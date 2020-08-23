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
    """
    Describes difference between two clients
    """
    def __init__(self, dest: str):
        self.destination: Path = Path(dest)
        self.add: FileStatDict = {}
        self.delete: FileStatDict = {}


async def get_diff(local: str, remote: str,
                depth:int=10, find_delete:bool=False,
                dry_run:bool=False, dump_delta:str=None) -> Delta:
    """
    Returns the difference between local and remote.
    """
    debug('[Main] WELCOME TO DRY RUN WHERE YOU CAN DO WHATEVER YOU WANT!')
    debug('[Main] Fetching local and remote file list')
    local_files = await get_local_files(local, max_depth=depth)
    remote_files = await get_remote_files(remote, max_depth=depth)
    debug('[Main] Done fetching local and remote file list')

    delta = Delta(remote)
    debug(f'[Delta] Start processing files, {len(local_files)} local, {len(remote_files)} remote')
    if find_delete:
        delete_list = [check_local_exist(relname, local_files) for relname in remote_files.keys()]
        delete_list = [(x, remote_files[x]) for x in delete_list if x is not None]
        delta.delete = dict(delete_list)
    
    update_list = [check_should_update(relname, local_files, remote_files) for relname in local_files.keys()]
    update_list = [(x, local_files[x]) for x in update_list if x is not None]
    delta.add = dict(update_list)
    debug(f'[Delta] Done processing files. {len(delta.delete)} to delete, {len(delta.add)} to add')

    if config.is_debug or dry_run:
        show_delta(delta)
    if dump_delta:
        dump_delta_to_file(delta, dump_delta)
    return delta


async def del_remote(delta: Delta, batch_size:int=100, dry_run:bool=False) -> None:
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

        if not dry_run:
            proc = await asyncio.create_subprocess_exec(*adb_command)
            result = await proc.communicate()
            log_adb_error(proc, result)
        slider.update(batch_size)


async def send_remote(delta: Delta, batch_size:int=5, dry_run:bool=False):
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

            if not dry_run:
                proc = await asyncio.create_subprocess_exec(*adb_command,
                                                            stdout=asyncio.subprocess.PIPE,
                                                            stderr=asyncio.subprocess.STDOUT,
                                                            stdin=asyncio.subprocess.DEVNULL)
                send_queue.append(proc)
        if not dry_run:
            proc_result = await asyncio.gather(*[proc.communicate() for proc in send_queue])
            for proc, comm_result in zip(send_queue, proc_result):
                log_adb_error(proc, comm_result)
        slider.update(batch_size)


def check_local_exist(relname: str, local: FileStatDict) -> str:
    """
    Checks if file exists remotely, meaning that it should be deleted
    Returns str or None
    """
    return relname if relname not in local else None


def check_should_update(relname: str, local: FileStatDict, remote: FileStatDict) -> str:
    """
    Checks or file existence, file size and file mtime.
    Returns str or None
    """
    if relname not in remote:
        return relname
    lf = local[relname]
    rf = remote[relname]
    if (lf.size != rf.size) or (lf.mtime > rf.mtime):
        return relname
    return None

def show_delta(delta: Delta):
    """
    Prints the delta in stdout
    """
    for relname in delta.delete: print(f'[Log] Deleting: {relname}')
    for relname in delta.add: print(f'[Log] Adding: {relname}')

def dump_delta_to_file(delta: Delta, delta_path: str):
    """
    Dumps the delta in a file.
    This contains more information
    """
    class PathEncoder(json.JSONEncoder):
        def default(self, o):
            if hasattr(o, '__dict__'):
                return o.__dict__
            if isinstance(o, Path):
                return str(o)
    
    with open(delta_path, 'w') as f:
        json.dump(delta, f, indent=4, cls=PathEncoder)
        f.close()