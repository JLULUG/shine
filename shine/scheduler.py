import logging as log
import threading
from time import time, sleep

from .daemon import evt, Task, tasks, lock, _windup, save, config


def sched() -> None:
    with lock:
        # fix inconsistent state
        for task in tasks.values():
            if task.state == Task.SYNCING:
                log.warning(f'task {task.name} was syncing, marked as failed')
                task.last_finish = int(time())
                task.state = Task.FAILED
                task.next_sched = task.retry()
        save()
        evt('sched:load')
    log.warning('started')
    while not _windup.is_set():
        # sleep for a while
        try:
            sleep_interval = int(config.get('interval', 10))
        except ValueError:
            log.exception('interval should be int')
            sleep_interval = 10
        sleep(sleep_interval)
        with lock:
            # check whether ready to run a new task
            log.debug('schedule slot, checking limit')
            skip = {'skip': False}
            evt('sched:limit', skip)
            if skip.get('skip', False):
                continue
            evt('sched:pre')
            # check runnable tasks
            log.debug('checking runnables')
            runnables = [
                task
                for task in tasks.values()
                if task.on
                and task.state != task.SYNCING
                and task.next_sched <= int(time())
                and task.condition()
            ]
            log.debug(f'runnables: {[ task.name for task in runnables ]}')
            if not runnables:
                continue
            # select a runnable
            evt('sched:select', locals())
            try:
                ratio = int(config.get('priority_ratio', 60))
            except ValueError:
                log.exception('priority_ratio should be int')
                ratio = 60
            next_task = max(
                runnables,
                key=lambda t: t.priority*ratio+t.waited
            )
            log.debug(f'next_task: {next_task.name}'
                f'({next_task.priority}*{ratio}+{next_task.waited})')
            # raise priority of other runnables
            evt('sched:selected', locals())
            for task in runnables:
                if task is not next_task:
                    task.waited += 1
            next_task.waited = 0
            save()
            # start the task
            threading.Thread(
                target=next_task.thread,
                name=next_task.name
            ).start()
            log.debug('new task started')
            evt('sched:post', locals())
