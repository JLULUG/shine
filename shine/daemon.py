import typing as t
import logging as log
import os
import sys
import json
import signal
import threading
from time import sleep
from functools import wraps
from types import FunctionType, MethodType

CONFIG_DIR = os.getenv('CONFIGURATION_DIRECTORY', '.')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.py')
PLUGINS_DIR = os.path.join(CONFIG_DIR, 'plugins')
MIRRORS_DIR = os.path.join(CONFIG_DIR, 'mirrors')
STATE_DIR = os.getenv('STATE_DIRECTORY', '.')
STATE_FILE = os.path.join(STATE_DIR, 'state.json')
RUN_DIR = os.getenv('RUNTIME_DIRECTORY', '.')
COMM_SOCK = os.path.join(RUN_DIR, 'shined.sock')
API_DIR = os.path.join(RUN_DIR, 'api')
LOG_DIR = os.getenv('LOGS_DIRECTORY', './log/')
os.makedirs(API_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

config: dict[str, t.Any] = {}
tasks: dict[str, 'Task'] = {}
lock = threading.RLock()
_windup = threading.Event()
_load_err = threading.Event()


def save() -> bool:
    evt(':save')
    log.debug('saving state')
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump([
                task.__dict__
                for task in tasks.values()
            ], f, default=lambda _: None, skipkeys=True)
        return True
    except (OSError, ValueError):
        log.exception('failed saving state!!')
        return False


def _scandir_py(path: str) -> list[os.DirEntry[str]]:
    try:
        return [
            file
            for file in os.scandir(path)
            if not file.name.startswith('.')
            and file.name.endswith('.py')
            and file.is_file()
        ]
    except (OSError, ValueError):
        log.exception(f'failed reading dir {dir}!!')
        _load_err.set()
        return []


def _exec(file_name: str, local: t.Optional[dict[str, t.Any]] = None) -> bool:
    try:
        with open(file_name, 'rb') as f:
            # pylint: disable-next=exec-used
            exec(compile(f.read(), f.name, 'exec'), globals(), local)
        return True
    except Exception:  # pylint: disable=broad-except
        log.exception(f'exception loading file {file_name}!!')
        _load_err.set()
        return False


def load_plugins() -> None:
    evt.clear()
    for file in _scandir_py(PLUGINS_DIR):
        log.info(f'loading plugin {file.name}')
        _exec(file.path)
    log.debug(f'evt registry: {repr(evt.registry)}')
    evt(':plugins_load')


def load_config() -> None:
    config.clear()
    log.info(f'loading config from {CONFIG_FILE}')
    _exec(CONFIG_FILE, config)
    log.debug(f'config: {repr(config)}')
    evt(':config_load')


def _bind_method(task: 'Task', method: str, f: FunctionType) -> MethodType:
    # no throw wrapping for custom method
    @wraps(f)
    def wrapper(*args, **kwargs):  # type: ignore
        try:
            return f(*args, **kwargs)
        except Exception:  # pylint: disable=broad-except
            log.exception('exception in task method, using default implementation')
            return Task.__dict__.get(method)(*args, **kwargs)  # type: ignore
    return MethodType(wrapper, task)


def load_mirrors() -> None:
    # make sure removed mirrors kept disabled
    for task in tasks.values():
        task.on = False
    for file in _scandir_py(MIRRORS_DIR):
        log.info(f'loading mirror {file.name}')
        task_config: dict[str, t.Any] = {}
        if not _exec(file.path, task_config):
            continue  # skip on exception
        name = task_config.get('name')
        if not name or not isinstance(name, str):
            log.error(f'"name" not present in mirror config {file.name}')
            _load_err.set()
            continue
        tasks.setdefault(name, Task())
        task = tasks[name]
        for k, v in task_config.items():
            if isinstance(v, FunctionType):
                if (
                    not isinstance(Task.__dict__.get(k), FunctionType)
                    and k[0].islower()
                ):
                    log.error(f'set prototype Task.{k} before overriding public method')
                    _load_err.set()
                    continue
                v = _bind_method(task, k, v)
            orig = Task().__dict__.get(k)
            if (orig is not None) and (type(v) is not type(orig)):
                log.error(f'builtin attribute "{k}" should be of type {type(orig)}')
                _load_err.set()
                continue
            task.__dict__[k] = v

    log.info(f'mirrors: {repr(list(tasks.keys()))}')
    for task in tasks.values():
        if not task.on and task.state != Task.SYNCING:
            log.info(f'disabling task {task.name}')
            task.state = Task.PAUSED
    evt(':mirrors_load')


def reload(_signum: int = 0, _frame: t.Any = None) -> bool:
    log.warning('(re)loading plugins, config and mirrors')
    _load_err.clear()
    evt(':reload')
    with lock:
        load_plugins()
        load_config()
        load_mirrors()
        save()
    evt(':load')
    return not _load_err.is_set()


def grace(_signum: int = 0, _frame: t.Any = None) -> None:
    if not _windup.is_set():
        _windup.set()
        log.warning('gracefully shutting down')
        evt(':grace')
        while [ 1 for task in tasks.values() if task.state == Task.SYNCING ]:
            sleep(5)
    clean(0)


def clean(signum: int = 0, _frame: t.Any = None) -> None:
    log.warning('doing final saving')
    evt(':clean')
    with lock:
        save()
    evt(':exit')
    log.warning('goodbye')
    if signum:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        os.killpg(0, signal.SIGTERM)
    sys.exit(0)


def main() -> None:
    # setup logger
    log.basicConfig(
        format='[%(levelname)s] %(threadName)s: %(message)s',
        level=(
            log.DEBUG if os.environ.get('DEBUG')
            else log.WARNING if os.environ.get('QUIET')
            else log.INFO
        )
    )

    # load state
    log.info(f'loading state from {STATE_FILE}')
    try:
        with open(STATE_FILE, 'rb') as f:
            state = json.load(f)
        for task in state:
            tasks[task['name']] = Task(task)
    except FileNotFoundError:
        log.warning('state file not found')
    except (OSError, KeyError, ValueError):
        log.critical('error loading state file', exc_info=True)
        sys.exit(1)

    # load plugins, config, mirrors
    if not reload():
        log.critical('error loading plugins/config/mirrors. refuse to start.')
        sys.exit(1)

    # setup signal handlers
    signal.signal(signal.SIGHUP, reload)
    signal.signal(signal.SIGINT, grace)
    signal.signal(signal.SIGTERM, clean)

    # start command thread
    threading.Thread(target=comm, name='comm', daemon=True).start()

    # start scheduler thread
    log.warning('starting scheduler')
    th_sched = threading.Thread(target=sched, name='sched', daemon=True)
    th_sched.start()
    log.warning('started')

    # ensure main & sched alive
    th_sched.join()
    log.critical('sched thread terminated unexpectedly! going down...')


# pylint: disable=wrong-import-position
# pylint: disable=unused-import
# pylint: disable=cyclic-import
from .eventmgr import evt, event_handler
from .task import Task
from .command import comm
from .scheduler import sched

# pylint: disable-next=wildcard-import,unused-wildcard-import
from .helpers import *
