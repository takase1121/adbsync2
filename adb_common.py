from typing import List, Tuple
from asyncio import create_subprocess_exec, subprocess

from common import log_adb_error

import config


def make_adb_command(subcommand: str) -> List[str]:
    """Creates a list of adb commands"""
    adb_command = ['adb']
    if config.device:
        adb_command = [*adb_command, '-t', config.device]
    adb_command.append(subcommand)
    return adb_command

async def run_adb_command(command: List[str]) -> Tuple[bool, str]:
    """Run adb command"""
    proc = await create_subprocess_exec(*command, 
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL)

    proc_output = await proc.communicate()
    has_error = log_adb_error(proc, proc_output)
    return (has_error, proc_output[0].decode(encoding='utf-8'))


def escape_sh_str(s: str) -> str:
    """
    Escapes the string for shell.
    Escapes quote by "gluing" string literals. Eg:
    "You're dumb" -> 'You'"'"'re dumb'
    Notice the double quotes. There are actually 3 string literals there
    """
    return "'" + s.replace("'", "'\"'\"'") + "'"
