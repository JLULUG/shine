import typing as t
import logging as log
import os
import signal
import socket
import threading
from time import time
from types import MethodType

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


def _time_duration(secs: float) -> str:
    secs = int(secs)
    h = abs(secs)//3600
    m = abs(secs)%3600//60
    s = abs(secs)%60
    return (
        ('-' if secs<0 else '')
        +(f'{h}h' if h else '')
        +(f'{m}m' if m else '')
        +(f'{s}s' if s and not h else '')
        +('now' if not secs else '')
    )


def show(_: str = '') -> str:
    with lock:
        res = []
        for task in tasks.values():
            res.append((
                ('!' if task.fail_count else '') + ('~' if not task.on else '') + task.name,
                'SUCCESS' if not task.fail_count else f'{task.fail_count} FAIL',
                _time_duration(time()-task.last_finish),
                f'RUNNING {_time_duration(time()-task.last_start)}' \
                if task.active else _time_duration(task.next_sched-time()),
            ))
        res.sort(key=lambda x: x[0].lower())
        # table printing
        res.insert(0, ('NAME', 'STATUS', 'LAST', 'NEXT'))
        width = [ max(len(x[i]) for x in res)+1 for i in range(4) ]
        return '\n'.join([
            ''.join([ f'{x[i]:<{width[i]}}' for i in range(4) ])
            for x in res
        ])


def info(task: Task) -> str:
    r = f'{task.name} ('+('on' if task.on else 'off')
    if not task.fail_count:
        r += f'; success {_time_duration(time()-task.last_success)}'
    else:
        r += f'; failed({task.fail_count}) {_time_duration(time()-task.last_finish)}'
    if task.active:
        r += f'; running {_time_duration(time()-task.last_start)})\n'
    else:
        r += f'; next {_time_duration(task.next_sched-time())})\n'
    for attr, val in task.__dict__.items():
        if attr in {'name', 'on', 'fail_count', '_loaded', '_config'}:
            continue
        if isinstance(val, MethodType):
            r += f'{attr}: {val.__doc__ or val}\n'
        else:
            r += f'{attr}: {val}\n'
    r += '\nConfig:\n'
    # pylint: disable-next=protected-access
    r += ''.join([ f'{k}: {v}\n' for k, v in task._config.items() ])
    return r


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
    save()
    log.info(f'{task.name} on')
    return 'Enabled.'


def disable(task: Task) -> str:
    if not task.on:
        return 'Task not enabled.'
    task.on = False
    save()
    log.info(f'{task.name} disabled')
    return 'Disabled.'


def remove(task: Task) -> str:
    if task.active:
        log.warning(f'cannot remove running task {task.name}')
        return 'Task still running.'
    tasks.pop(task.name)
    save()
    log.warning(f'{task.name} removed')
    return 'Task state removed, please delete config manually.'


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
    'reload': ('Reload plugins and tasks', reload),
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
