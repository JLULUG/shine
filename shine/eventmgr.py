import typing as t
import logging as log

from .daemon import lock

AnyCallable = t.Callable[[t.Any], t.Any]


class EventManager:
    def __init__(self) -> None:
        self.registry: dict[str, list[AnyCallable]] = {}

    def registered(self, event: str, callback: AnyCallable) -> bool:
        return callback in self.registry.get(event, [])

    def deregister(self, event: str, callback: AnyCallable) -> None:
        if self.registered(event, callback):
            log.debug(f'deregister {callback} from event {event}')
            self.registry[event].remove(callback)

    def register(self, event: str, callback: AnyCallable, insert: bool=False) -> None:
        log.debug(f'register {callback} to event {event}')
        self.registry.setdefault(event, [])
        if insert:
            self.registry[event].insert(0, callback)
        else:
            self.registry[event].append(callback)

    def __call__(self, event: str, arg: t.Optional[t.Any] = None) -> None:
        log.debug(f'event {event}')
        with lock:
            for callback in self.registry.get(event, []):
                try:
                    callback(arg)
                except Exception:  # pylint: disable=broad-except
                    log.exception(f'exception caught in plugins handling {event}')


def event_handler(event: str, insert: bool=False) -> t.Callable[[AnyCallable], AnyCallable]:
    def decorator(f: AnyCallable) -> AnyCallable:
        evt.register(event, f, insert)
        return f
    return decorator


evt = EventManager()
