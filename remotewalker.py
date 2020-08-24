import asyncio

from tqdm import tqdm

import config
from common import chunks, log_adb_error, log_adb_command, debug
from adb_common import make_adb_command, escape_sh_str

from filestructs import RemoteFileStat, FileStatDict


async def get_remote_files(path: str, max_depth: int = 1, output_dict: FileStatDict = {}) -> FileStatDict:
    """
    This uses find. May not be available in most systems, but I don't care.
    Updated to use find and stat seperately with chunking to reduce overhead
    """
    adb_command = make_adb_command('shell')
    adb_command = [*adb_command, 'find', path, '-type', 'f', '-maxdepth', str(max_depth)]
    
    log_adb_command(adb_command)
    find_proc = await asyncio.create_subprocess_exec(*adb_command,
                                                    stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.DEVNULL,
                                                    stdin=asyncio.subprocess.DEVNULL)
    find_stdout, _ = await find_proc.communicate()
    if find_proc.returncode != 0:
        return output_dict
    
    find_stdout = find_stdout.decode(encoding='utf-8').splitlines()
    slider = tqdm(total=len(find_stdout), desc=f'[RemoteWalker] Running stat on file list')
    for find_slice in chunks(find_stdout):
        find_slice = map(escape_sh_str, find_slice)
        adb_command = make_adb_command('shell')
        adb_command = [*adb_command, 'stat', '-c', '%N:%f:%s:%y', *find_slice]
        
        if config.debug_stat: log_adb_command(adb_command)
        stat_proc = await asyncio.create_subprocess_exec(*adb_command,
                                                    stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.DEVNULL,
                                                    stdin=asyncio.subprocess.DEVNULL)
        stat_stdout, _ = await stat_proc.communicate()
        if not log_adb_error(stat_proc, stat_stdout):
            for line in stat_stdout.decode(encoding='utf-8').splitlines():
                stats = RemoteFileStat(path, line, ':')
                output_dict[stats.relname] = stats
                slider.update(1)

    return output_dict
