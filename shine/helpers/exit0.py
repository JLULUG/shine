import typing as t

from ..daemon import Task


def Exit0(
    f: t.Callable[[Task], tuple[int, t.Any]]
) -> t.Callable[[Task], bool]:
    """Wrap a runner to check exit code at tuple[0] to be zero"""
    def run(self: Task) -> bool:
        ret, *_ = f(self)
        return ret == 0

    return run
