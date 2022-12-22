import typing as t
import logging as log
import os
import sys
import json
import signal
import threading
from functools import wraps
from types import FunctionType, MethodType

CONFIG_DIR = os.getenv('CONFIGURATION_DIRECTORY', '.')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.py')
PLUGINS_DIR = os.path.join(CONFIG_DIR, 'plugins')
TASKS_DIR = os.path.join(CONFIG_DIR, 'tasks')
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
load_err = threading.Event()


def save() -> bool:
    if load_err.is_set():
        log.error('refuse to save after load error, reload first')
        return False
    evt(':save')
    log.debug('saving state')
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump([
                {
                    k: v
                    for k, v in task.__dict__.items()
                    if not k.startswith('_')
                    and isinstance(v, (int, float, bool, str, dict, list))
                }
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
        load_err.set()
        return []


def _exec(file_name: str, local: t.Optional[dict[str, t.Any]] = None) -> bool:
    try:
        with open(file_name, 'rb') as f:
            # pylint: disable-next=exec-used
            exec(compile(f.read(), f.name, 'exec'), globals(), local)
        return True
    except Exception:  # pylint: disable=broad-except
        log.exception(f'exception loading file {file_name}!!')
        load_err.set()
        return False


def load_plugins() -> None:
    evt.registry.clear()
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


def _bind_method(
    task: 'Task',
    method: str,
    f: t.Callable[..., t.Any]
) -> MethodType:
    # no throw wrapping for custom method
    @wraps(f)
    def wrapper(*args, **kwargs):  # type: ignore
        try:
            return f(*args, **kwargs)
        except Exception:  # pylint: disable=broad-except
            if method in Task.__dict__:
                log.exception('exception in task method, using default implementation')
                return Task.__dict__[method](*args, **kwargs)
            raise

    return MethodType(wrapper, task)


def load_tasks() -> None:
    _bare_task = Task()
    for task in tasks.values():
        setattr(task, '_loaded', False)
    for file in _scandir_py(TASKS_DIR):
        log.info(f'loading task {file.name}')
        task_config: dict[str, t.Any] = {}
        if not _exec(file.path, task_config):
            continue  # skip on exception
        name = task_config.get('name')
        if not name or not isinstance(name, str):
            log.error(f'name not present in task config {file.name}')
            load_err.set()
            continue
        tasks.setdefault(name, Task())
        task = tasks[name]
        setattr(task, '_loaded', True)
        for attr, val in task_config.items():
            if attr in helpers.__all__:
                continue
            if isinstance(val, FunctionType):
                val = _bind_method(task, attr, val)
            try:
                # pylint: disable-next=unnecessary-dunder-call
                default = _bare_task.__getattribute__(attr)
                if type(val) is not type(default):
                    log.error(f'builtin attribute "{attr}" should be of type {type(default)}')
                    load_err.set()
                    continue
                setattr(task, attr, val)
            except AttributeError:
                task._config[attr] = val  # pylint: disable=protected-access

    log.info(f'tasks: {repr(list(tasks.keys()))}')
    for task in tasks.values():
        if not getattr(task, '_loaded', False):
            log.info(f'disabling orphan task {task.name}')
            task.on = False
    evt(':tasks_load')


def reload(_signum: int = 0, _frame: t.Any = None) -> bool:
    log.warning('(re)loading plugins, config and tasks')
    evt(':reload')
    with lock:
        load_err.clear()
        load_plugins()
        load_config()
        load_tasks()
        if not save():
            load_err.set()
    evt(':load')
    return not load_err.is_set()


def clean(signum: int = 0, _frame: t.Any = None) -> None:
    log.warning('stopping tasks')
    with lock:
        for task in tasks.values():
            if task.active:
                task.kill()
        log.warning('doing final saving')
        evt(':clean')
        save()
        evt(':exit')
        log.warning('goodbye')
        signal.signal(signal.SIGTERM, signal.SIG_DFL if signum else signal.SIG_IGN)
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
        log.critical('error loading state file!!!', exc_info=True)
        sys.exit(1)

    # load plugins, config, tasks
    if not reload():
        log.critical('error loading plugins/config/tasks. refuse to start.')
        sys.exit(1)

    # setup signal handlers
    signal.signal(signal.SIGHUP, reload)
    signal.signal(signal.SIGINT, clean)
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
    clean()


# pylint: disable=wrong-import-position
# pylint: disable=unused-import
# pylint: disable=cyclic-import
from .eventmgr import evt, event_handler
from .task import Task
from .command import comm
from .scheduler import sched

# pylint: disable=wildcard-import,unused-wildcard-import
from . import helpers
from .helpers import *
