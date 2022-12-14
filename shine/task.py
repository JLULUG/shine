import typing as t
import logging as log
import os
from time import time, strftime, localtime

from .daemon import LOG_DIR, evt, save, lock


class Task:
    # pylint: disable=too-many-instance-attributes
    # task states constant
    PAUSED = 0
    SUCCCESS = 1
    SYNCING = 2
    FAILED = 3

    # *: (usually) required in config
    # -: don't set in config
    # +: supplied in config or by plugins
    def __init__(self, _dict: t.Optional[dict[str, t.Any]] = None) -> None:
        # ** canonical name of mirror
        self.name: str = ''
        # ** is scheduling
        self.on: bool = False
        # * static priority in config
        self.priority: float = 1
        # - mirror status
        self.state: int = Task.PAUSED
        # - last successful sync finished at
        self.last_update: int = 0
        # - current/last sync started at
        self.last_start: int = 0
        # - last successful/failed sync finished at
        self.last_finish: int = 0
        # - earliest next run scheduled at
        self.next_sched: int = 0
        # - retry interval doubles each failure
        self.fail_count: int = 0
        # + description
        self.description: t.Optional[str] = None
        # + category
        self.category: t.Optional[str] = None
        # + storage size used
        self.size: t.Optional[int] = None
        # + web path
        self.url: t.Optional[str] = None
        # + upstream server
        self.upstream: t.Optional[str] = None
        # load state
        self.__dict__.update(_dict or {})
        # - running pids
        self.pids: list[int] = []

    # prevent AttributeError
    def __getattr__(self, _attr: str) -> None:
        return None

    # - size in 'xxx GiB' string
    @property
    def size_str(self) -> t.Optional[str]:
        if self.size is None:
            return None
        suffix = ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi']
        try:
            size = float(self.size)
            if size < 0:
                raise ValueError('size must be positive')
        except (ArithmeticError, ValueError):
            log.exception('illegal task.size')
        while len(suffix)>1 and size >= 1024:
            suffix.pop(0)
            size /= 1024
        return f'{str(round(size, 2)).rstrip("0").rstrip(".")} {suffix[0]}B'

    # + arbitrary extra condition for task excution
    def condition(self) -> bool:
        return True

    # + arbitrary job before run()
    def pre(self) -> None:
        pass

    # - log file path for this task
    def log_file(self, prefix: str = 'log') -> str:
        file_name = f'{self.name}-{strftime("%Y%m%d-%H%M%S")}.log'
        if prefix and isinstance(prefix, str):
            file_name = prefix+'-'+file_name
        return os.path.join(LOG_DIR, file_name)

    # * task runner, usually specified with a helper
    def run(self) -> bool:
        log.warning(f'using default runner for task {self.name}')
        return False

    # * decide next task schedule
    def next(self) -> int:
        log.warning(f'using default scheduler for task {self.name}')
        return int(time())+24*60*60

    # + custom next() retry for failed run
    def retry(self) -> int:
        normal = self.next()
        failed = int(time())+30*int(2**self.fail_count)
        return min(normal, failed)

    # + arbitrary job after run()
    def post(self) -> None:
        pass

    # - task controller, don't change unless absolutely necessary
    def thread(self) -> None:
        log.info('task started')
        with lock:
            self.state = Task.SYNCING
            self.last_start = int(time())
            save()
        evt('task:pre', self)
        log.debug('task pre()')
        self.pre()
        log.debug('task run()')
        result = self.run()
        with lock:
            if result:
                self.state = Task.SUCCCESS
                self.last_update = int(time())
                self.next_sched = self.next()
                self.fail_count = 0
                evt('task:success', self)
                log.info('task succeeded')
            else:
                self.state = Task.FAILED
                self.next_sched = self.retry()
                self.fail_count += 1
                evt('task:fail', self)
                log.info(f'task failed({self.fail_count})')
            log.info(f'next schedule '
                     f'{strftime("%Y-%m-%d %H:%M:%S", localtime(self.next_sched))}')
            if not self.on:  # if disabled during sync
                log.info(f'disabling task {self.name}')
                self.state = Task.PAUSED
            self.last_finish = int(time())
            save()
        log.debug('task post()')
        self.post()
        evt('task:post', self)
        log.debug('task ended')
