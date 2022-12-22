import typing as t
import logging as log
from datetime import datetime, timedelta

from ..daemon import Task


def Cron(
    cron_spec: str,  # see `man crontab(5)`
) -> t.Callable[[Task], int]:
    """Calculate next run using crontab syntax"""
    try:
        m_spec, h_spec, d_spec, mo_spec, w_spec = cron_spec.split()
        m_set = spec_to_set(m_spec, 0, 59)
        h_set = spec_to_set(h_spec, 0, 23)
        d_set = spec_to_set(d_spec, 1, 31)
        mo_set = spec_to_set(mo_spec, 1, 12)
        w_set = spec_to_set(w_spec, 0, 7)
    except (AttributeError, TypeError, ValueError):
        log.error('Cron: invalid syntax')
        raise

    if 0 in w_set:  # 0 or 7 is Sunday
        w_set.add(7)
        w_set.remove(0)
    log.debug(f'Cron: {cron_spec} -> {(m_set, h_set, d_set, mo_set, w_set)}')
    # Note: If both fields are restricted, the command will be run when either
    #       field matches the current time.
    day_both_set = len(d_set) != 31 and len(w_set) != 7
    # prevent Feb 31 from causing infinite loop
    if not day_both_set and (
        (mo_set <= {2, 4, 6, 9, 11} and d_set <= {31}) or
        (mo_set <= {2} and d_set <= {30, 31})
    ):
        raise ValueError('Cron: "day in month" condition cannot be met')

    def nxt(_self: Task) -> int:
        x = datetime.today()+timedelta(minutes=1)
        while True:
            if x.month not in mo_set:
                if x.month == 12:
                    x = x.replace(year=x.year+1, month=1, day=1, hour=0, minute=0)
                else:
                    x = x.replace(month=x.month+1, day=1, hour=0, minute=0)
            elif (  # TL;DR: any 2 cond of 3, see day_both_set above
                ((x.day not in d_set) and (x.isoweekday() not in w_set))
                if day_both_set else
                ((x.day not in d_set) or (x.isoweekday() not in w_set))
            ):
                x = x.replace(hour=0, minute=0)+timedelta(days=1)
            elif x.hour not in h_set:
                x = x.replace(minute=0)+timedelta(hours=1)
            elif x.minute not in m_set:
                x = x+timedelta(minutes=1)
            else:
                log.debug(f'Cron: next "{cron_spec}" is {x}')
                return int(x.timestamp())

    return nxt


def spec_to_set(spec: str, lower: int, upper: int) -> set[int]:
    """convert list/range/step notation to valid value set"""
    # A field may contain an asterisk (*), which always stands for "first-last".
    spec = spec.replace('*', f'{lower}-{upper}')
    # A list is a set of numbers (or ranges) separated by commas.
    ranges = spec.split(',')
    res: set[int] = set()
    for range_spec in ranges:
        if '/' not in range_spec:
            range_spec = range_spec + '/1'
        # Step values can be used in conjunction with ranges.
        range_spec, step_str = range_spec.split('/')
        step = int(step_str)
        if step <= 0:
            raise ValueError('Cron: step must be positive')
        if '-' not in range_spec:
            range_spec = range_spec + '-' + range_spec
        # Ranges are two numbers separated with a hyphen.
        frm, to = map(int, range_spec.split('-'))
        if not lower <= frm <= to <= upper:
            raise ValueError(f'Cron: {frm}-{to} should be within {lower}-{upper}')
        # Ranges are two numbers separated with a hyphen.  The specified range is inclusive.
        # Following a range with "/<number>" specifies skips of the values through the range.
        res.update(range(frm, to+1, step))
    return res
