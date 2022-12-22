import typing as t
import logging as log
import os
import threading
from time import time, strftime, localtime

from .daemon import LOG_DIR, evt, save, lock


class Task:
    def __init__(self, _dict: t.Optional[dict[str, t.Any]] = None) -> None:
        self.name: str = ''  # required in config
        self.on: bool = True
        self.last_success: int = 0
        self.last_start: int = 0
        self.last_finish: int = 0
        self.next_sched: int = 0
        self.fail_count: int = 0
        self._thread: t.Optional[threading.Thread] = None
        self.__dict__.update(_dict or {})
        self._config: dict[str, t.Any] = {}

    @property
    def active(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def __getattr__(self, attr: str) -> t.Any:
        return self._config.get(attr)

    # below:
    # *: required in config
    # +: may set in config

    # + arbitrary extra condition for task excution
    def condition(self) -> bool:
        return True

    # + arbitrary job before run()
    def pre(self) -> None:
        pass

    # - log file path for this task
    def log_file(self, prefix: str = '') -> str:
        file_name = f'{self.name}-{strftime("%Y%m%d-%H%M%S")}.log'
        if prefix and isinstance(prefix, str):
            file_name = prefix+'-'+file_name
        return os.path.join(LOG_DIR, file_name)

    # * task runner
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

    # + method to stop the task
    def kill(self) -> bool:
        return False

    # + arbitrary job after run()
    def post(self) -> None:
        pass

    # task controller, do NOT override
    def thread(self) -> None:
        log.info('task started')
        with lock:
            if self.active:  # exclusive
                return
            self._thread = threading.current_thread()
            self.last_start = int(time())
            save()
        evt('task:pre', self)
        log.debug('task pre()')
        self.pre()
        log.debug('task run()')
        result = self.run()
        log.debug('task post()')
        self.post()
        evt('task:post', self)
        with lock:
            if result:
                self.last_success = int(time())
                self.next_sched = self.next()
                self.fail_count = 0
                evt('task:success', self)
                log.info('task succeeded')
            else:
                self.next_sched = self.retry()
                self.fail_count += 1
                evt('task:fail', self)
                log.info(f'task failed({self.fail_count})')
            log.info(f'next schedule '
                     f'{strftime("%Y-%m-%d %H:%M:%S", localtime(self.next_sched))}')
            self.last_finish = int(time())
            self._thread = None
            save()
        log.debug('task ended')
