from os import linesep
from asyncio.subprocess import Process
from typing import Iterable, Tuple, Union
from logging import error, log, DEBUG
from tqdm import tqdm

import config

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def log_adb_command(command: Iterable[str], level: int = DEBUG):
    """Logs ADB command generated"""
    log(level, f'ADB command generated: {" ".join([*command])}')


def log_adb_error(proc: Process, proc_output: Tuple[bytes, bytes]):
    """Logs adb error from an asyncio.subprocess.Process instance and output from proc.communicate()"""
    if proc.returncode != 0:
        proc_stdout, proc_stderr = [stream.decode(encoding='utf-8') for stream in proc_output]
        error(
            '[Error] ADB command failed with non-zero return code.'
            + linesep
            + '> stdout'
            + linesep
            + linesep.join([f'--->{line}' for line in proc_stdout.splitlines()])
            + linesep
            + '> stderr'
            + linesep
            + linesep.join([f'--->{line}' for line in proc_stderr.splitlines()])
        )

    return proc.returncode != 0


def bar(iter: Union[Iterable, int], desc: str):
    """More elegant way to make progress bars"""
    if isinstance(iter, int):
        return tqdm(desc=desc, total=iter, unit='file(s)')
    else:
        return tqdm(iter, desc, unit='file(s)')