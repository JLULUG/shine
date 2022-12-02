import typing as t
import logging as log
from random import randint
from datetime import datetime, timedelta

from ..daemon import Task


def _time_conv(time: t.Union[int, str]) -> int:
    if isinstance(time, int):
        time = str(time) + 's'
    conversion = {'s': 1, 'm': 60, 'h': 60*60, 'd': 24*60*60, 'w': 7*24*60*60}
    if time[-1] not in conversion:
        raise ValueError('Interval: interval must end with s/m/h/d/w.')
    try:
        time_sec = int(time[:-1])*conversion[time[-1]]
    except (TypeError, ValueError):
        log.error('Interval: invalid interval')
        raise
    if not 0 <= time_sec < 10*365*24*60*60:
        raise ValueError('Interval: interval must be within 10 years')
    return time_sec

def Interval(
    interval: t.Union[int, str],  # second int or 25m/6h style str
    randomize: t.Union[int, str] = 0,
    avail_hours: str = '0-23'     # 0-5,22-23 style str
) -> t.Callable[[Task], int]:
    """Calculate next run by interval over available hours"""
    # convert list of ranges notation to valid value set
    try:
        hour_map = [0]*24
        hour_ranges = [ x.strip() for x in avail_hours.split(',') ]
        for hour_range in hour_ranges:
            if '-' in hour_range:
                start, end = [ int(x)%24 for x in hour_range.split('-') ]
                if end < start:
                    end += 24
                for x in range(start, end+1):  # [start, end)
                    hour_map[x%24] = 1
            else:
                hour_map[int(hour_range)%24] = 1
    except (AttributeError, TypeError, ValueError):
        log.error('Interval: invalid avail_hours syntax')
        raise
    if not sum(hour_map):
        raise ValueError('Interval: no available hour')

    interval_sec = _time_conv(interval)
    randomize_sec = _time_conv(randomize)
    log.debug(f'Interval: {interval} -> {interval_sec}(+{randomize_sec}), '
              f'{avail_hours} -> {hour_map}')

    def nxt(_self: Task) -> int:
        def next_hour(dt: datetime) -> datetime:
            return dt.replace(minute=0, second=0)+timedelta(hours=1)
        x = x0 = datetime.today().replace(microsecond=0)
        secs = max(0, interval_sec + randint(-randomize_sec, +randomize_sec))
        remain = timedelta(seconds=secs)
        if sum(hour_map) == 24:  # quick way for tasks without hour restriction
            x = x0+remain
        else:
            while remain:
                if not hour_map[x.hour]:  # current hour unavailable
                    x = next_hour(x)
                elif next_hour(x)-x < remain:  # fill current hour
                    remain -= next_hour(x)-x
                    x = next_hour(x)
                else:  # remaindar within current hour
                    x += remain
                    remain -= remain
        log.debug(f'Interval: {x0} + {secs}({avail_hours}) = {x}')
        return int(x.timestamp())

    return nxt
