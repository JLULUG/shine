import typing as t
import logging as log
from subprocess import Popen, PIPE, STDOUT, SubprocessError, TimeoutExpired

from ..daemon import Task


def System(
    cmd: list[str],                        # argv
    input_data: t.Optional[bytes] = None,  # stdin data
    timeout: t.Optional[int] = None,       # in seconds, passed to communicate()
    log_prefix: str = 'system',            # log file name prefix
    **popen_kwargs: t.Any                  # passed to Popen() constructor
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
                stdout=open(log_file, 'wb'),
                stderr=STDOUT,
                **popen_kwargs
            ) as process:
                log.debug(f'System: process pid: {process.pid}')
                self.pids.append(process.pid)
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
                self.pids.remove(process.pid)
                log.debug('System: process exited')
                if process.returncode != 0:
                    log.error(f'System: process exited with code {process.returncode}')
                return (process.returncode, log_file)
        except (OSError, ValueError, SubprocessError):
            log.exception('System: error executing the command')
            raise

    return run
