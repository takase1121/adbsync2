from typing import List

import config


def make_adb_command(subcommand: str) -> List[str]:
    """Creates a list of adb commands"""
    adb_command = ['adb']
    if config.device:
        adb_command = [*adb_command, '-t', config.device]
    adb_command.append(subcommand)
    return adb_command


def escape_sh_str(s: str) -> str:
    """
    Escapes the string for shell.
    Escapes quote by "gluing" string literals. Eg:
    "You're dumb" -> 'You'"'"'re dumb'
    Notice the double quotes. There are actually 3 string literals there
    """
    return "'" + s.replace("'", "'\"'\"'") + "'"