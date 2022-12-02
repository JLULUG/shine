import logging as log

from shine.daemon import config, Task, tasks, event_handler

# Config example:
# concurrency = 8


@event_handler('sched:limit')
def concurrent_limiter(skip: dict[str, bool]) -> None:
    if skip.get('skip', False):
        return
    max_concurrent = int(config.get('concurrency', 8))
    running = [ task for task in tasks.values() if task.state == Task.SYNCING ]
    log.debug(f'concurrent: {[ task.name for task in running ]}')
    if len(running) > max_concurrent:
        log.info('skipping schedule slot due to concurrency')
        skip['skip'] = True
