import typing as t
import logging as log

from .daemon import lock

AnyCallable = t.Callable[[t.Any], t.Any]


class EventManager:
    def __init__(self) -> None:
        self.registry: dict[str, list[AnyCallable]] = {}

    def register(self, event: str, callback: AnyCallable) -> None:
        log.debug(f'register {callback} to event {event}')
        self.registry.setdefault(event, [])
        self.registry[event].append(callback)

    def clear(self) -> None:
        self.registry = {}

    def __call__(self, event: str, arg: t.Optional[t.Any] = None) -> None:
        log.debug(f'event {event}')
        try:
            with lock:
                for callback in self.registry.get(event, []):
                    callback(arg)
        except Exception:  # pylint: disable=broad-except
            log.exception(f'exception caught in plugins handling {event}')


def event_handler(event: str) -> t.Callable[[AnyCallable], AnyCallable]:
    def decorator(f: AnyCallable) -> AnyCallable:
        evt.register(event, f)
        return f
    return decorator


evt = EventManager()
