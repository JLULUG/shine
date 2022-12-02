import logging as log
import os

from shine.daemon import config, event_handler

# Config example:
# load_limit = (4.0, 2.5, 0)
# 0 means no limit


@event_handler('sched:limit')
def load_limiter(skip: dict[str, bool]) -> None:
    if skip.get('skip', False):
        return
    load_limit = config.get('load_limit', (0, 0, 0))
    load = os.getloadavg()
    if (  # any non-zero value exceed
        (load_limit[0] and load[0] >= load_limit[0]) or
        (load_limit[1] and load[1] >= load_limit[1]) or
        (load_limit[2] and load[2] >= load_limit[2])
    ):
        log.info(f'skipping schedule slot due to load {load}')
        skip['skip'] = True
