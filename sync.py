import json
import asyncio
from pathlib import Path
from typing import List, Dict

from tqdm import tqdm

import config
from common import chunks, debug, log_adb_error, log_adb_command
from adb_common import make_adb_command, escape_sh_str

from filestructs import FileStat, FileStatDict
from localwalker import get_local_files
from remotewalker import get_remote_files


class Delta:
    """Describes difference between two clients"""
    def __init__(self, dest: str):
        self.destination: Path = Path(dest)
        self.add: FileStatDict = {}
        self.delete: FileStatDict = {}


async def get_diff(
        source: str, destination: str,
        max_depth: int = 10, delete_files: bool = False,
        delta_path: str = None) -> Delta:
    """Returns the difference between local and remote"""

    debug('[Main] WELCOME TO DRY RUN WHERE YOU CAN DO WHATEVER YOU WANT!')
    debug('[Main] Fetching local and remote file list')
    src_files = await get_local_files(source, max_depth=max_depth)
    dest_files = await get_remote_files(destination, max_depth=max_depth)
    debug('[Main] Done fetching local and remote file list')

    delta = Delta(destination)
    debug(f'[Delta] Start processing files, {len(src_files)} local, {len(dest_files)} remote')
    if delete_files:
        delete_list = [file for file in dest_files.items() if file[0] in src_files]
        delta.delete = dict(delete_list)
    
    update_list = [file for file in src_files.items() if delta_should_add(file[1], src_files, dest_files)]
    delta.add = dict(update_list)
    debug(f'[Delta] Done processing files. {len(delta.delete)} to delete, {len(delta.add)} to add')

    if config.debug_general or config.dry_run:
        show_delta(delta)
    if delta_path:
        dump_delta_to_file(delta, delta_path)
    return delta

async def del_remote(delta: Delta, batch_size: int = 100) -> None:
    """
    Delete files from remote with the rm command.
    """
    delete_iter = iter(delta.delete)
    slider = tqdm(total=len(delta.delete), desc='[Main] Deleting remote files')
    for chunk in chunks(delete_iter, n=batch_size):
        adb_command = make_adb_command('shell')
        adb_command = [
            *adb_command, 'rm', '-r',
            *[escape_sh_str(delta.delete[key].filename) for key in chunk]
        ]
        log_adb_command(adb_command)

        if not config.dry_run:
            proc = await asyncio.create_subprocess_exec(*adb_command, 
                                                        stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.STDOUT,
                                                        stdin=asyncio.subprocess.DEVNULL)
            result = await proc.communicate()
            log_adb_error(proc, result)
        slider.update(batch_size)

async def send_remote(delta: Delta, batch_size: int = 5) -> None:
    """
    Send files to remote with adb push.
    adb is run in parallel to increase speed.
    This could be turned of by setting batch_size to 1
    """
    send_iter = iter(delta.add)
    slider = tqdm(total=len(delta.add), desc='[Main] Pushing files to remote')
    for chunk in chunks(send_iter, n=batch_size):
        send_queue = []
        for filename in chunk:
            stat = delta.add[filename]
            destination = delta.destination / stat.relname
            adb_command = make_adb_command('push')
            adb_command.append(stat.filename)
            adb_command.append(destination.as_posix())
            log_adb_command(adb_command)

            if not config.dry_run:
                proc = await asyncio.create_subprocess_exec(*adb_command,
                                                            stdout=asyncio.subprocess.PIPE,
                                                            stderr=asyncio.subprocess.STDOUT,
                                                            stdin=asyncio.subprocess.DEVNULL)
                send_queue.append(proc)
        if not config.dry_run:
            proc_result = await asyncio.gather(*[proc.communicate() for proc in send_queue])
            for proc, comm_result in zip(send_queue, proc_result):
                log_adb_error(proc, comm_result)
        slider.update(batch_size)


def delta_should_add(local_file: FileStat, src: FileStatDict, dest: FileStatDict) -> bool:
    """Checks or file existence, file size and file mtime"""
    if local_file.relname not in dest:
        return True
    remote_file = dest[local_file.relname]
    if local_file.size != remote_file.size or local_file.size > remote_file.mtime:
        return True
    return False


def show_delta(delta: Delta):
    """Prints the delta in stdout"""
    for relname in delta.delete: print(f'[Log] Deleting: {relname}')
    for relname in delta.add: print(f'[Log] Adding: {relname}')

def dump_delta_to_file(delta: Delta, delta_path: str):
    """Dumps the delta in a JSON file"""
    class PathEncoder(json.JSONEncoder):
        def default(self, o):
            if hasattr(o, '__dict__'):
                return o.__dict__
            if isinstance(o, Path):
                return str(o)
    
    with open(delta_path, 'w') as f:
        json.dump(delta, f, indent=4, cls=PathEncoder)