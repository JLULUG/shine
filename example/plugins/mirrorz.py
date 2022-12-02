import typing as t
import logging as log
import os
import json

from shine.daemon import API_DIR, config, Task, tasks, evt, event_handler

MIRRORZ_FILE = os.path.join(API_DIR, 'mirrorz.json')

# Config example:
"""
mirrorz_site = {
    'url': 'https://example.org',
    'logo': 'https://example.org/img/logo.svg',
    'logo_darkmode': 'https://example.org/img/logo-white.svg',
    'abbr': 'EXAMPLE',
    'name': 'example mirrors',
    'homepage': 'https://blog.example.org',
    'issue': 'https://github.com/example/issues',
    'request': 'https://github.com/example/mirror-request',
    'email': 'admin@example.com',
    'group': 'QQ: 10086 and/or Telegram @something',
    'disk': 'may be any string showing usage of disk, e.g. usage',
    'note': 'may be any string; like speed limit or connection limit',
    'big': '/speedtest/1000mb.bin'
}
"""


@event_handler(':save')
def mirrorz(_: t.Any) -> None:
    """see https://github.com/mirrorz-org/mirrorz"""
    mirrorz_data: dict[str, t.Any] = {
        'version': 1.5,
        'site': config.get('mirrorz_site'),  # dict
        'info': [],
        'mirrors': [],
    }
    # this event handler should supply the 'info' part
    evt('mirrorz:info', mirrorz_data)

    for task in tasks.values():
        task_data: dict[str, t.Optional[str]] = {}
        task_data['cname'] = task.name
        status_conv: dict[int, t.Callable[[Task], str]] = {
            Task.PAUSED: lambda task: f'P{task.last_update}',
            Task.SUCCCESS: lambda task: f'S{task.last_update}X{task.next_sched}',
            Task.SYNCING: lambda task: f'Y{task.last_start}O{task.last_update}',
            Task.FAILED: lambda task: f'F{task.last_finish}X{task.next_sched}O{task.last_update}',
        }
        task_data['status'] = status_conv.get(task.state, lambda _: 'U')(task)
        task_data['desc'] = task.desc
        task_data['size'] = task.size_str
        task_data['url'] = task.url
        task_data['help'] = task.help_url
        task_data['upstream'] = task.upstream
        if isinstance(task.mirrorz_data, dict):  # custom data dict per task
            task_data.update(task.mirrorz_data)
        # only strings allowed
        task_data = { k: v for k, v in task_data.items() if isinstance(v, str) }
        mirrorz_data['mirrors'].append(task_data)

    # this event is for arbitrary data manipulation
    evt('mirrorz:data', mirrorz_data)
    log.debug('mirrorz: saving')
    with open(MIRRORZ_FILE, 'w', encoding='utf-8') as f:
        json.dump(mirrorz_data, f)
