import logging as log
import threading
from time import time, sleep

from .daemon import evt, tasks, lock, save

interval = 10  # pylint: disable=invalid-name


def sched() -> None:
    with lock:
        for task in tasks.values():
            # fix inconsistent state
            if task.last_start > task.last_finish:
                log.warning(f'rescheduling task {task.name}')
                task.fail_count += 1
                task.last_finish = int(time())
                task.next_sched = int(time())
        save()
    evt('sched:load')
    log.warning('started')
    while True:
        # sleep for a while
        sleep(interval)
        with lock:
            log.debug('schedule slot')
            evt('sched:pre')
            # check runnable tasks
            log.debug('checking runnables')
            runnables = [  # filter by trivial criteria
                task
                for task in tasks.values()
                if task.on and not task.active
                and task.next_sched <= int(time()) + interval
            ]
            evt('sched:runnables', runnables)  # filter by plugins
            runnables = [  # filter by custom condition
                task
                for task in runnables
                if task.condition()
            ]
            log.debug(f'runnables: {[ task.name for task in runnables ]}')
            if not runnables:
                continue
            # select a runnable
            evt('sched:select', locals())
            next_task = max(
                runnables,
                key=lambda t: (t.priority or 1.0)*(time()+interval-t.next_sched)
            )
            log.debug(f'next_task: {next_task.name}')
            save()
            # start the task
            threading.Thread(
                target=next_task.thread,
                name=next_task.name
            ).start()
            log.debug('new task started')
            evt('sched:post', locals())
