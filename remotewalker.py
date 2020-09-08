import asyncio
import shlex

import config
from common import chunks, log_adb_command, bar
from adb_common import make_adb_command, run_adb_command

from filestructs import RemoteFileStat, FileStatDict


async def get_remote_files(path: str, max_depth: int = 1, output_dict: FileStatDict = {}) -> FileStatDict:
    """
    This uses find. May not be available in most systems, but I don't care.
    Updated to use find and stat seperately with chunking to reduce overhead
    """
    base_adb_command = make_adb_command('shell')
    adb_command = [
        *base_adb_command,
        'find', path, '-type', 'f', '-maxdepth', str(max_depth)
    ]
    log_adb_command(adb_command)

    errored, find_output = await run_adb_command(adb_command, combine=False, bypass_dry_run=True)
    if errored:
        raise Exception('Unable to run find command on remote')
    
    find_output = find_output.splitlines()
    with bar(len(find_output), f'INFO:{__name__}:Creating remote file list') as slider:
        for find_slice in chunks(find_output, config.command_batch_size):
            adb_command = [
                *base_adb_command, 'stat', '-c', '%N:%s:%Y',
                *map(shlex.quote, find_slice)
            ]
            log_adb_command(adb_command)

            errored, output = await run_adb_command(adb_command, combine=False, bypass_dry_run=True)
            if not errored:
                for line in output.splitlines():
                    file_stat = RemoteFileStat(path, line, ':')
                    output_dict[file_stat.relname] = file_stat
            slider.update(config.command_batch_size)

    return output_dict
