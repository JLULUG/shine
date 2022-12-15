import typing as t
import logging as log
import os
import signal
import socket
import threading
from time import time

from . import VERSION
from . import daemon
from .daemon import COMM_SOCK, Task, tasks, save, lock, evt


def usage(*_: t.Any) -> str:
    r = f'Shine v{VERSION}\n\nUsage:\n'
    for k, v in handlers.items():
        r += f'{k : <10}{v[0]}\n'
    return r


def show(*_: t.Any) -> str:
    # TODO prettify
    with lock:
        return repr(tasks)


def info(task: Task) -> str:
    # TODO prettify
    return repr(task.__dict__)


def start(task: Task) -> str:
    if task.state == Task.SYNCING:
        return 'Task already running.'
    log.warning(f'force starting {task.name}')
    threading.Thread(
        target=Task.thread,
        args=(task,),
        name=task.name
    ).start()
    return 'Started.'


def stop(task: Task) -> str:
    if task.state != Task.SYNCING:
        return 'Task already stopped.'
    log.warning(f'force stopping {task.name}')
    if not task.kill():
        return 'Failed to stop the task.'
    return 'Stopping attempted.'


def enable(task: Task) -> str:
    if task.on:
        return 'Task not disabled.'
    task.on = True
    if task.state == Task.PAUSED:
        task.next_sched = int(time())
    save()
    log.info(f'{task.name} on')
    return info(task)+'\nEnabled this run.'


def disable(task: Task) -> str:
    if not task.on:
        return 'Task not enabled.'
    task.on = False
    if task.state != Task.SYNCING:
        task.state = Task.PAUSED
    save()
    log.info(f'{task.name} disabled')
    return info(task)+'\nDisabled this run.'


def remove(task: Task) -> str:
    if task.state == Task.SYNCING:
        log.warning(f'cannot remove running task {task.name}')
        return 'Task still running.'
    tasks.pop(task.name)
    save()
    log.warning(f'{task.name} removed')
    return 'Removed.'


def reload(*_: t.Any) -> str:
    if not daemon.reload():
        return 'Error occured reconfiguring. Check log output for details.'
    return 'Reconfigured.'


def grace(*_: t.Any) -> str:
    os.kill(0, signal.SIGINT)
    return 'Gracefully shutting down.'


def kill(*_: t.Any) -> str:
    os.kill(0, signal.SIGTERM)
    return 'Goodbye.'


handlers: dict[str, tuple[str, t.Callable[..., str]]] = {
    'help': ('Show this help', usage),
    'show': ('Print status', show),
    'info': ('Print <task> details', info),
    'start': ('Force a <task> to start', start),
    'stop': ('Force a <task> to stop', stop),
    'enable': ('Enable a <task> (runtime)', enable),
    'disable': ('Disable a <task> (runtime)', disable),
    'remove': ('Remove a <task> state', remove),
    'reload': ('Reload plugins, config and mirrors', reload),
    'grace': ('Gracefully shutdown after finishing tasks', grace),
    'KiLL': ('Kill all tasks and shutdown', kill),
}


def handle(conn: socket.socket) -> None:
    with conn:
        file = conn.makefile(encoding='utf-8', errors='ignore')
        while True:
            line_b = file.readline()
            if not line_b:  # empty means EOF
                break
            line = line_b.split(maxsplit=1)
            if not line:  # only blank means empty line
                continue
            log.info(f'command: {repr(line)}')
            handler = handlers.get(line[0], handlers['help'])
            if '<task>' in handler[0]:  # command with <task> argument
                with lock:
                    if len(line) < 2:  # missing parameter
                        result = usage()
                    elif line[1].strip() not in tasks:
                        result = 'Task not found.'
                    else:
                        result = handler[1](tasks[line[1].strip()])
            else:
                result = handler[1](line[1:])
            log.debug(f'response: {repr(result)}')
            result_b = result.encode('utf-8', errors='ignore')
            conn.sendall(int.to_bytes(len(result_b), 4, 'big'))
            conn.sendall(result_b)


def comm() -> None:
    try:
        try:
            os.remove(COMM_SOCK)
        except FileNotFoundError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(COMM_SOCK)
        sock.listen(1)
        log.warning('started')
    except OSError:
        log.critical('failed creating socket! going down...')
        kill()

    while True:
        conn, _ = sock.accept()
        log.info('new connection')
        threading.Thread(
            target=handle,
            args=(conn,),
            name=f'comm-{conn.fileno()}'
        ).start()
