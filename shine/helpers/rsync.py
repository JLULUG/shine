import typing as t
import logging as log
import re
from datetime import datetime, timedelta

from ..daemon import Task
from .system import System

DEFAULT_OPTIONS = [
    '-vrltpH', '--no-h', '--stats', '--safe-links',
    '--delete-after', '--delay-updates', '-f', '-p .~tmp~/', '-f', 'R .~tmp~/'
]

EXIT_CODE = {  # base on rsync 3.2.6
    1: 'Syntax or usage error',
    2: 'Protocol incompatibility',
    3: 'Errors selecting input/output files, dirs',
    4: 'Requested action not supported.',
    5: 'Error starting client-server protocol',
    6: 'Daemon unable to append to log-file',
    10: 'Error in socket I/O',
    11: 'Error in file I/O',
    12: 'Error in rsync protocol data stream',
    13: 'Errors with program diagnostics',
    14: 'Error in IPC code',
    20: 'Received SIGUSR1 or SIGINT',
    21: 'Some error returned by waitpid()',
    22: 'Error allocating core memory buffers',
    23: 'Partial transfer due to error',
    24: 'Partial transfer due to vanished source files',
    25: 'The --max-delete limit stopped deletions',
    30: 'Timeout in data send/receive',
    35: 'Timeout waiting for daemon connection',
}


def Rsync(
    # pylint: disable=too-many-arguments
    upstream: str,  # ends with / 'rsync://example.com/example/',
    local: str,
	options: t.Optional[list[str]] = None,
    exclude: t.Optional[list[str]] = None,
    password: t.Optional[str] = None,
    timeout: t.Optional[int] = None,
	env: t.Optional[dict[str, str]] = None,
    enable_pre_stage: bool = False,
    pre_stage_extra: t.Optional[list[str]] = None,
	io_timeout: int = 60,
	excutable: str = 'rsync',
    no_default_options: bool = False,
    no_extract_size: bool = False,
    **popen_kwargs: t.Any
) -> t.Callable[[Task], tuple[int, str]]:
    # pylint: disable=too-many-locals
    options = options or []
    exclude = exclude or []
    env = env or {}
    pre_stage_extra = pre_stage_extra or []

    if password is not None:
        env['RSYNC_PASSWORD'] = password
    if timeout and timeout > 365*24*60*60:
        raise ValueError('Rsync: timeout too big')
    if io_timeout:
        options.append(f'--timeout={io_timeout}')
    if no_default_options is False:
        options = DEFAULT_OPTIONS + options

    argv = ([excutable] + options + exclude + [upstream, local])
    if enable_pre_stage:
        pre_stage_argv = list(filter(
            lambda x: not x.startswith('--delete'),
            [excutable] + options + pre_stage_extra + exclude + [upstream, local]
        ))

    def run(self: Task) -> tuple[int, str]:
        if timeout:
            stop_time = datetime.today()+timedelta(seconds=timeout)
            stop_at = [f'--stop-at={stop_time.strftime("%Y-%m-%dT%H:%M")}']
        else:
            stop_at = []

        if enable_pre_stage:
            pre_stage_ret, pre_stage_out = System(
                pre_stage_argv + stop_at,
                log_prefix='rsync',
                env=env,
                **popen_kwargs
            )(self)
            if pre_stage_ret != 0:
                log.error(
                    f'Rsync: pre stage failed with code {pre_stage_ret}: '
                    f'{EXIT_CODE.get(pre_stage_ret, "")}'
                )
                return (pre_stage_ret, pre_stage_out)

        ret, out = System(
            argv + stop_at,
            log_prefix='rsync',
            env=env,
            **popen_kwargs
        )(self)
        if ret != 0:
            log.error(f'Rsync: failed with code {ret}: {EXIT_CODE.get(ret, "")}')
            return (ret, out)

        log.debug('Rsync: success')

        if not no_extract_size:
            try:
                with open(out, 'r', encoding='utf-8', errors='ignore') as f:
                    match = re.findall(
                        r'^Total file size: ([0-9]+) bytes',
                        f.read(),
                        re.MULTILINE
                    )
                self.size = int(match[-1])
                log.info(f'Rsync: total size {self.size_str}')
            except (OSError, IndexError, TypeError, ValueError):
                log.exception('Rsync: failed extracting size from log')

        return (ret, out)

    return run
