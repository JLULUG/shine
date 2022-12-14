import typing as t
import logging as log
import os
import signal
from subprocess import Popen, PIPE, STDOUT, SubprocessError, TimeoutExpired

from ..daemon import Task, _bind_method


def System(
    # pylint: disable=too-many-arguments
    cmd: list[str],  # argv
    input_data: t.Optional[bytes] = None,  # stdin data
    timeout: t.Optional[int] = None,  # in seconds, passed to communicate()
    log_prefix: str = 'system',  # passed to task.log_file()
    log_append: bool = False,  # open log file with wb or ab
    **popen_kwargs: t.Any,  # passed to Popen() constructor
) -> t.Callable[[Task], tuple[int, str]]:
    """Run command specified with timeout, returns exit code and output"""

    def run(self: Task) -> tuple[int, str]:
        if input_data is not None:
            popen_kwargs['stdin'] = PIPE
        log_file = self.log_file(log_prefix)
        log.info(f'System: running {cmd} timeout {timeout}')
        log.debug(f'System: popen_kwargs: {popen_kwargs}')
        try:
            with Popen(
                cmd,
                stdout=open(log_file, 'ab' if log_append else 'wb'),
                stderr=STDOUT,
                **popen_kwargs,
            ) as process:
                log.debug(f'System: process pid: {process.pid}')
                setattr(self, '_system_pid', process.pid)
                setattr(self, 'kill', _bind_method(self, 'kill', kill_pid))
                try:
                    process.communicate(input_data, timeout=timeout)
                except TimeoutExpired:
                    log.warning('System: process timed out, terminating')
                    process.terminate()
                    while process.poll() is None:  # keep trying to kill
                        try:
                            process.wait(timeout=10)
                        except TimeoutExpired:
                            log.error('System: process did not exit, killing')
                            process.kill()
                delattr(self, '_system_pid')
                log.debug('System: process exited')
                if process.returncode != 0:
                    log.error(f'System: process exited with code {process.returncode}')
                return (process.returncode, log_file)
        except (OSError, ValueError, SubprocessError):
            log.exception('System: error executing the command')
            raise

    run.__doc__ = f'System({cmd}' + (f', timeout={timeout})' if timeout else ')')
    return run


def kill_pid(self: Task) -> bool:
    pid = getattr(self, '_system_pid', None)
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        log.exception(f'error killing {pid}')
        return False
