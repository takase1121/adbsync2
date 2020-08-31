import json
import asyncio
from enum import Enum
from typing import List, Dict, Iterable
from itertools import chain
from pathlib import Path
from datetime import datetime

from tqdm import tqdm

import config
from common import chunks, debug, log_adb_command
from adb_common import make_adb_command, run_adb_command, escape_sh_str

from filestructs import FileStat, FileStatDict
from localwalker import get_local_files
from remotewalker import get_remote_files


class SyncDirection(Enum):
    """Sync direction"""
    PHONE_TO_MACHINE = 1
    MACHINE_TO_PHONE = 2


class Delta:
    direction: SyncDirection = None
    destination: Path = None
    upload: FileStatDict = {}
    remove: FileStatDict = {}

    def __init__(self, direction: SyncDirection, dest: str):
        """Describes difference between two clients"""
        self.direction = direction
        self.destination: Path = Path(dest)


async def get_diff(
        source: str, destination: str,
        max_depth: int = 10, delete_files: bool = False,
        delta_path: str = None) -> Delta:
    """Returns the difference between local and remote"""
    direction = None
    local_path, remote_path = None, None
    # check for sync direction from source and destination
    if is_mobile_path(source):
        is_valid_mobile_path(source)
        direction = SyncDirection.PHONE_TO_MACHINE
        local_path, remote_path = destination, source[source.find(':') + 1:]
    elif is_mobile_path(destination):
        is_valid_mobile_path(destination)
        direction = SyncDirection.MACHINE_TO_PHONE
        # removing the mobile path part from the path, we only need the path from now on
        destination = destination[destination.find(':') + 1:]
        local_path, remote_path = source, destination
    else:
        raise Exception('No phone specified')

    if (direction == SyncDirection.PHONE_TO_MACHINE and is_mobile_path(destination) or
        direction == SyncDirection.MACHINE_TO_PHONE and is_mobile_path(source)):
        raise Exception('Cannot sync from phone to phone')

    if config.dry_run: debug('[Main] WELCOME TO DRY RUN WHERE YOU CAN DO WHATEVER YOU WANT!')
    debug('[Main] Fetching local and remote file list')
    local_files = await get_local_files(local_path, max_depth=max_depth)
    remote_files = await get_remote_files(remote_path, max_depth=max_depth)
    debug('[Main] Done fetching local and remote file list')

    # destination can be local path or remote path so it's save either way
    delta = Delta(direction, destination)
    debug(f'[Delta] Start processing files, {len(local_files)} local, {len(remote_files)} remote')
    if delete_files:
        delete_list = ([file for file in remote_files.items() if file[0] not in local_files]
                            if direction == SyncDirection.MACHINE_TO_PHONE else
                        [file for file in local_files.items() if file[0] not in remote_files])
        delta.remove = dict(delete_list)
    
    update_list = ([file for file in local_files.items() if delta_should_add(file[1], local_files, remote_files)]
                        if direction == SyncDirection.MACHINE_TO_PHONE else
                    [file for file in remote_files.items() if delta_should_add(file[1], remote_files, local_files)])
    delta.upload = dict(update_list)
    debug(f'[Delta] Done processing files. {len(delta.remove)} to delete, {len(delta.upload)} to add')

    if config.debug_general or config.dry_run:
        show_delta(delta)
    if delta_path:
        dump_delta_to_file(delta, delta_path)
    return delta


async def del_remote(delta: Delta, batch_size: int = 100) -> None:
    """Delete files from remote with the rm command"""
    with tqdm(total=len(delta.remove),
                desc='[Main] Deleting remote files', unit='file') as slider:

        base_adb_command = make_adb_command('shell')
        for chunk in chunks(delta.remove.items(), n=batch_size):
            adb_command = [
                *base_adb_command, 'rm', '-r',
                *[escape_sh_str(file_stat.filename) for _, file_stat in chunk]
            ]
            log_adb_command(adb_command)

            if not config.dry_run:
                await run_adb_command(adb_command)
            slider.update(batch_size)

async def del_local(delta: Delta) -> None:
    """Delete local files"""
    delete_iter = tqdm(delta.remove.items(), desc='[Main] Deleting local files', unit='file')
    for _, file_stat in delete_iter:
        p = Path(file_stat.filename)
        p.unlink(missing_ok=True)


async def send_to_remote(delta: Delta, batch_size: int = 5) -> None:
    """
    Send files to remote with adb push.
    adb is run in parallel to increase speed.
    This could be turned of by setting batch_size to 1
    NOTE: in order to actually preserve metadata, we have to send and touch the file.
    I hate you Android.
    """
    def run_cmd(file_stat: FileStat):
            source = file_stat.filename
            destination = delta.destination / file_stat.relname
            adb_command = [*make_adb_command('push'), source, destination.as_posix()]
            log_adb_command(adb_command)
            return run_adb_command(adb_command)
    
    with tqdm(total=len(delta.upload),
                desc='[Main] Pushing files to remote', unit='file') as slider:        
        for chunk in chunks(delta.upload.items(), n=batch_size):
            send_queue = [run_cmd(file_stat) for _, file_stat in chunk if not config.dry_run]
            send_result = await asyncio.gather(*send_queue)
            filtered_chunk = [c for c, (errored, _) in zip(chunk, send_result) if not errored]
            
            await touch_files(delta.destination, filtered_chunk)
            slider.update(batch_size)

async def send_to_local(delta: Delta, batch_size: int = 5) -> None:
    """Pull files from remote to local"""
    base_adb_command = make_adb_command('pull')
    base_adb_command.append('-a')
    def run_cmd(file_stat: FileStat):
        source = file_stat.filename
        destination = delta.destination / file_stat.relname
        # mkdir parent path just in case because adb on Windows will error
        destination.parent.mkdir(parents=True, exist_ok=True)
        adb_command = [*base_adb_command, source, str(destination)]
        log_adb_command(adb_command)
        return run_adb_command(adb_command)

    with tqdm(total=len(delta.upload),
                desc='[Main] Pulling files to local', unit='file') as slider:
        for chunk in chunks(delta.upload.items(), n=batch_size):
            await asyncio.gather(*[run_cmd(file_stat) for _, file_stat in chunk if not config.dry_run])
            slider.update(batch_size)


async def touch_files(dest: Path, chunk: Iterable[FileStat]) -> List[str]:
    """Creates a very long list of adb shell + touch command. should be more efficient"""
    base_adb_command = make_adb_command('shell')
    def generate_cmd(file_stat: FileStat):
        destination = dest / file_stat.relname
        return [
            'touch', '-cmd',
            escape_sh_str(datetime.fromtimestamp(file_stat.mtime).strftime('%Y-%m-%d%H:%M:%S')),
            escape_sh_str(destination.as_posix()),
            ';'
        ]

    if not config.dry_run:
        adb_command = chain.from_iterable([generate_cmd(file_stat) for _, file_stat in chunk if not config.dry_run])
        adb_command = [*base_adb_command, *adb_command]
        await run_adb_command(adb_command)


def show_delta(delta: Delta):
    """Prints the delta in stdout"""
    for relname in delta.remove: print(f'[Log] Deleting: {relname}')
    for relname in delta.upload: print(f'[Log] Adding: {relname}')

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


def delta_should_add(src_file: FileStat, src: FileStatDict, dest: FileStatDict) -> bool:
    """Checks or file existence, file size and file mtime"""
    if src_file.relname not in dest:
        return True
    dest_file = dest[src_file.relname]
    if (src_file.size != dest_file.size) or (src_file.mtime > dest_file.mtime):
        return True
    return False


def is_mobile_path(s: str) -> bool:
    """
    Checks if path specified points to a phone
    On windows, path can have a drive letter and that adds : to the path.
    To overcome that we only check for `:` that is not the second letter of string,
    where the drive letter colon should always be.
    """
    idx = s.find(':')
    return idx > 1

def is_valid_mobile_path(s: str) -> None:
    """
    This will raise a ValueError if the mobile path is invalid
    A valid mobile path is [ADB_ID OR 'remote']:path
    """
    s_slice = s[:s.find(':')]
    if s_slice != 'remote' and not s_slice.isnumeric():
        raise ValueError('Invalid mobile path')