import typing as t
import logging as log
import os
import json
from time import strftime, localtime

from shine.daemon import API_DIR, Task, tasks, evt, event_handler

TUNASYNC_FILE = os.path.join(API_DIR, 'tunasync.json')


@event_handler(':save')
def tunasync_json(_: t.Any) -> None:
    status_conv: dict[int, str] = {
        Task.PAUSED: 'paused',
        Task.SUCCCESS: 'success',
        Task.SYNCING: 'syncing',
        Task.FAILED: 'failed',
    }
    fmt_time: t.Callable[[int], str] = (
        lambda x: strftime('%Y-%m-%d %H:%M:%S %z', localtime(x))
    )
    tunasync_data: list[dict[str, t.Any]] = [
        {
            'name': task.name,
            'is_master': True,
            'status': status_conv.get(task.state, ''),
            'last_update': fmt_time(task.last_update),
            'last_update_ts': task.last_update,
            'last_started': fmt_time(task.last_start),
            'last_started_ts': task.last_start,
            'last_ended': fmt_time(task.last_finish),
            'last_ended_ts': task.last_finish,
            'next_schedule': fmt_time(task.next_sched),
            'next_schedule_ts': task.next_sched,
            'upstream': task.upstream or '',
            'size': task.size_str or '',
        }
        for task in tasks.values()
    ]
    tunasync_data = sorted(tunasync_data, key=lambda x: x.get('name', ''))

    # this event is for arbitrary data manipulation
    evt('tunasync:data', tunasync_data)
    log.debug('tunasync: saving')
    with open(TUNASYNC_FILE, 'w', encoding='utf-8') as f:
        json.dump(tunasync_data, f)
