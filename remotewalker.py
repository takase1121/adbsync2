import asyncio

from tqdm import tqdm

import config
from common import chunks, log_adb_command
from adb_common import make_adb_command, run_adb_command, escape_sh_str

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

    errored, find_output = await run_adb_command(adb_command)
    if errored:
        return output_dict
    
    find_output = find_output.splitlines()
    with tqdm(total=len(find_output),
                desc=f'[RemoteWalker] Running stat on file list', unit='file') as slider:
        for find_slice in chunks(find_output, n=100):
            adb_command = [
                *base_adb_command, 'stat', '-c', '%N:%s:%Y',
                *[escape_sh_str(filename) for filename in find_slice]
            ]
            if config.debug_stat: log_adb_command(adb_command)

            errored, output = await run_adb_command(adb_command)
            if not errored:
                for line in output.splitlines():
                    file_stat = RemoteFileStat(path, line, ':')
                    output_dict[file_stat.relname] = file_stat
            slider.update(100)

    return output_dict
