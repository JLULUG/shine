import typing as t

from ..daemon import Task


def Earliest(*f: t.Callable[[Task], int]) -> t.Callable[[Task], int]:
    """Use the earliest schedule of multiple functions"""

    def nxt(self: Task) -> int:
        return min(x(self) for x in f)

    nxt.__doc__ = f'Earliest({", ".join(x.__doc__ or str(x) for x in f)})'
    return nxt
