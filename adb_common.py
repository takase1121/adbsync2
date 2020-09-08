from typing import List, Tuple
from asyncio import create_subprocess_exec, subprocess

from common import log_adb_error, log_adb_command

import config


def make_adb_command(subcommand: str) -> List[str]:
    """Creates a list of adb commands"""
    adb_command = ['adb']
    if config.device:
        adb_command = [*adb_command, '-t', config.device]
    adb_command.append(subcommand)
    return adb_command


async def run_adb_command(command: List[str], combine: bool = True, bypass_dry_run: bool = False) -> Tuple[bool, str]:
    """Run adb command"""
    log_adb_command(command)
    if config.dry_run and not bypass_dry_run:
        return False, ''
    proc = await create_subprocess_exec(*command, 
                                        stdout=subprocess.PIPE,
                                        stderr=(subprocess.STDOUT if combine else subprocess.PIPE),
                                        stdin=subprocess.DEVNULL)

    proc_output = await proc.communicate()
    has_error = log_adb_error(proc, proc_output)
    return has_error, proc_output[0].decode(encoding='utf-8')