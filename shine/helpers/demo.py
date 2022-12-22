import typing as t
import logging as log
from time import sleep
from random import random, randint

from ..daemon import Task


def Demo(
    time_min: int,
    time_max: int,
    error_rate: float = 0.0
) -> t.Callable[[Task], bool]:
    """Sleep for a random period of time, fail at chance"""
    def run(_self: Task) -> bool:
        duration = randint(time_min, time_max)
        log.debug(f'Demo: sleeping for {duration} minutes')
        sleep(duration*60)
        return not random() < error_rate

    return run
