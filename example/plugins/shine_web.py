import typing as t
import logging as log
import os
import json

from shine.daemon import API_DIR, Task, tasks, evt, event_handler

SHINE_WEB_FILE = os.path.join(API_DIR, 'shine.json')
SHINE_TMP_FILE = os.path.join(API_DIR, 'shine.json.tmp')


@event_handler(':save')
def shine_web_json(_: t.Any) -> None:
    status_conv: dict[int, str] = {
        Task.PAUSED: 'paused',
        Task.SUCCCESS: 'success',
        Task.SYNCING: 'syncing',
        Task.FAILED: 'failed',
    }
    shine_web_data: list[dict[str, t.Any]] = [
        {
            'name': task.name,
            'status': status_conv.get(task.state, ''),
            'last_update': task.last_update,
            'last_start': task.last_start,
            'last_finish': task.last_finish,
            'next_schedule': task.next_sched
        }
        for task in tasks.values()
    ]

    # this event is for arbitrary data manipulation
    evt('shine_web:data', shine_web_data)
    log.debug('shine_web: saving')
    with open(SHINE_TMP_FILE, 'w', encoding='utf-8') as f:
        json.dump(shine_web_data, f)
    os.replace(SHINE_TMP_FILE, SHINE_WEB_FILE)
