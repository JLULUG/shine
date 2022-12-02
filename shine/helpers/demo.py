import typing as t
import logging as log
from time import sleep
from random import randint

from ..daemon import Task


def Demo(
    time_min: int,
    time_max: int,
    error_rate: int = 0
) -> t.Callable[[Task], bool]:
    def run(_self: Task) -> bool:
        duration = randint(time_min, time_max)
        log.debug(f'Demo: sleeping for {duration} minutes')
        sleep(duration*60)
        if randint(0, 100) < error_rate*100:
            return False
        return True

    return run
