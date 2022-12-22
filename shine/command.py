import typing as t
import logging as log
import os
import json
import signal
import socket
import threading
from time import time

from . import VERSION
from . import daemon
from .daemon import COMM_SOCK, Task, tasks, save, lock


def usage(_: str = '') -> str:
    r = f'Shine v{VERSION}\n'
    r += '\nGlobal commands:\n'
    r += ''.join([
        f'{k : <10}{v[0]}\n'
        for k, v in global_cmd.items()
    ])
    r += '\nPer-task commands:\n'
    r += ''.join([
        f'{k : <10}{v[0]}\n'
        for k, v in per_task_cmd.items()
    ])
    return r


def show(_: str = '') -> str:
    # TODO prettify
    with lock:
        return '\n'.join([
            repr(task.__dict__)
            for task in tasks.values()
        ])


def info(task: Task) -> str:
    # TODO prettify
    return json.dumps(task.__dict__, indent=4, default=repr, skipkeys=True)


def start(task: Task) -> str:
    if task.active:
        return 'Task already running.'
    log.warning(f'force starting {task.name}')
    threading.Thread(
        target=task.thread,
        name=task.name
    ).start()
    return 'Started.'


def stop(task: Task) -> str:
    if not task.active:
        return 'Task is not running.'
    log.warning(f'force stopping {task.name}')
    if not task.kill():
        return 'Failed to stop the task.'
    return 'Stopping attempted.'


def enable(task: Task) -> str:
    if task.on:
        return 'Task not disabled.'
    task.on = True
    if not task.active:
        task.next_sched = int(time())
    save()
    log.info(f'{task.name} on')
    return info(task)+'\nEnabled.'


def disable(task: Task) -> str:
    if not task.on:
        return 'Task not enabled.'
    task.on = False
    save()
    log.info(f'{task.name} disabled')
    return info(task)+'\nDisabled.'


def remove(task: Task) -> str:
    if task.active:
        log.warning(f'cannot remove running task {task.name}')
        return 'Task still running.'
    tasks.pop(task.name)
    save()
    log.warning(f'{task.name} removed')
    return 'Task state removed.'


def reload(_: str = '') -> str:
    if not daemon.reload():
        return 'Error occured reconfiguring. Check log output for details.'
    return 'Reconfigured.'


def kill(_: str = '') -> str:
    os.kill(0, signal.SIGTERM)
    return 'Goodbye.'


global_cmd: dict[str, tuple[str, t.Callable[[str], str]]] = {
    'help': ('Show this help', usage),
    'show': ('Print status', show),
    'reload': ('Reload plugins, config and tasks', reload),
    'KiLL': ('Kill all tasks and shutdown', kill),
}

per_task_cmd: dict[str, tuple[str, t.Callable[[Task], str]]] = {
    'info': ('Print <task> details', info),
    'start': ('Force a <task> to start', start),
    'stop': ('Force a <task> to stop', stop),
    'enable': ('Enable a <task>', enable),
    'disable': ('Disable a <task>', disable),
    'remove': ('Remove a <task> state', remove),
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
            if line[0] in global_cmd:
                result = global_cmd[line[0]][1]((line+[''])[1].strip())  # default to empty
            elif line[0] in per_task_cmd:
                with lock:
                    if len(line) < 2:  # missing parameter
                        result = 'Task not specified'
                    elif line[1].strip() not in tasks:
                        result = 'Task not found.'
                    else:
                        result = per_task_cmd[line[0]][1](tasks[line[1].strip()])
            else:
                result = usage()
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
