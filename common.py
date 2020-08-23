from os import linesep
from itertools import zip_longest
from asyncio.subprocess import Process
from typing import Iterable, Callable, Tuple

import config


def debug(*args):
    """
    Used to print debug lines
    """
    if config.is_debug:
        print(*args)


def chunks(iterable: Iterable, n:int=100):
    """
    Returns an iterator that returns the source in chunks
    of n
    """
    args = [iter(iterable)] * n
    return [[entry for entry in zip_output if entry is not None] for zip_output in zip_longest(*args)]


def log_adb_command(command: Iterable[str]):
    """
    Logs ADB command generated
    """
    debug('[ADB] Command generated:', *command)


def log_adb_error(proc: Process, comm_output: Tuple[str, str]):
    """
    Logs adb error from an asyncio.subprocess.Process instance
    and output from proc.communicate()
    """
    if proc.returncode != 0:
        comm_output = comm_output[0].decode(encoding='utf-8')
        print(
            '[Error] ADB returned non zero return code:'
            + linesep
            + linesep.join([f'--->{line}' for line in comm_output.splitlines()])
        )
        return True
    return False
