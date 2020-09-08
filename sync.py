import json
import asyncio
import shlex
from enum import Enum
from typing import List, Dict, Tuple
from pathlib import Path
from itertools import chain
from datetime import datetime
from logging import info


import config
from common import chunks, bar
from adb_common import make_adb_command, run_adb_command
from filestructs import FileStat, FileStatDict
from localwalker import get_local_files
from remotewalker import get_remote_files


class SyncDirection(Enum):
    """Sync direction"""
    PHONE_TO_MACHINE = 1
    MACHINE_TO_PHONE = 2


class Delta:
    direction: SyncDirection = None
    local_path: Path = None
    remote_path: Path = None
    upload: List[FileStat] = None
    remove: List[FileStat] = []

    def __init__(self, direction: SyncDirection, local_path: str, remote_path: str):
        """Describes difference between two clients"""
        self.direction = direction
        self.local_path = Path(local_path)
        self.remote_path = Path(remote_path)


async def get_diff(
        source: str, destination: str,
        max_depth: int = 10, delete_files: bool = False,
        delta_path: str = None) -> Delta:
    """Returns the difference between local and remote"""
    direction = None
    source, destination = source.strip(), destination.strip()
    local_path, remote_path = None, None
    # check for sync direction from source and destination
    if mobile_path(source) and not mobile_path(destination):
        device, device_path = parse_mobile_path(source)
        config.device = device
        direction = SyncDirection.PHONE_TO_MACHINE
        local_path, remote_path = destination, device_path
    elif mobile_path(destination) and not mobile_path(source):
        device, device_path = parse_mobile_path(destination)
        config.device = device
        direction = SyncDirection.MACHINE_TO_PHONE
        local_path, remote_path = source, device_path
    else:
        raise Exception('Invalid sync direction or path')

    if config.dry_run: info('Dry run enabled')
    info('Fetching local and remote file list')
    local_files = await get_local_files(local_path, max_depth)
    remote_files = await get_remote_files(remote_path, max_depth)
    info('Done fetching local and remote file list')

    # destination can be local path or remote path so it's save either way
    delta = Delta(direction, local_path, remote_path)
    info(f'Start processing files, {len(local_files)} local, {len(remote_files)} remote')
    if delete_files:
        delta.remove = ([stat for relname, stat in remote_files.items() if relname not in local_files]
                            if direction == SyncDirection.MACHINE_TO_PHONE else
                        [stat for relname, stat in local_files.items() if relname not in remote_files])
    
    delta.upload = ([stat for stat in local_files.values() if delta_should_add(stat, local_files, remote_files)]
                        if direction == SyncDirection.MACHINE_TO_PHONE else
                    [stat for stat in remote_files.values() if delta_should_add(stat, remote_files, local_files)])
    info(f'Done processing files. {len(delta.remove)} to delete, {len(delta.upload)} to add')

    if delta_path:
        dump_delta_to_file(delta, delta_path)
    return delta


async def del_remote(delta: Delta) -> None:
    """Delete files from remote with the rm command"""
    with bar(len(delta.remove), f'INFO:{__name__}:Deleting remote files') as progress:
        base_adb_command = make_adb_command('shell')
        for chunk in chunks(delta.remove, config.command_batch_size):
            adb_command = [
                *base_adb_command,
                'rm', '-r',
                *[shlex.quote(file_stat.filename) for file_stat in chunk]
            ]
            await run_adb_command(adb_command)
            progress.update(config.command_batch_size)

async def del_local(delta: Delta) -> None:
    """Delete local files"""
    for file_stat in bar(delta.remove, f'INFO:{__name__}:Deleting local files'):
        p = Path(file_stat.filename)
        p.unlink(missing_ok=True)


async def send_to_remote(delta: Delta) -> None:
    """
    Send files to remote with adb push.
    adb is run in parallel to increase speed.
    This could be turned of by setting batch_size to 1
    NOTE: in order to actually preserve metadata, we have to send and touch the file.
    I hate you Android.
    """
    base_adb_command = make_adb_command('push')
    def run_cmd(file_stat: FileStat):
            source = file_stat.filename
            destination = delta.remote_path / file_stat.relname
            adb_command = [*base_adb_command, source, destination.as_posix()]
            return run_adb_command(adb_command)
    
    with bar(len(delta.upload), f'INFO:{__name__}:Pushing files to remote') as progress:    
        for chunk in chunks(delta.upload, config.adb_batch_size):
            send_queue = map(run_cmd, chunk)
            send_result = await asyncio.gather(*send_queue)
            filtered_chunk = [stat for stat, (errored, _) in zip(chunk, send_result) if not errored]
            
            await touch_files(delta, filtered_chunk)
            progress.update(config.adb_batch_size)

async def send_to_local(delta: Delta) -> None:
    """Pull files from remote to local"""
    base_adb_command = [*make_adb_command('pull'), '-a']
    def run_cmd(file_stat: FileStat):
        source = file_stat.filename
        destination = delta.local_path / file_stat.relname
        # mkdir parent path just in case because adb on Windows will error
        destination.parent.mkdir(parents=True, exist_ok=True)
        adb_command = [*base_adb_command, source, str(destination)]
        return run_adb_command(adb_command)

    with bar(len(delta.upload), f'INFO:{__name__}:Pulling files to local') as progress:
        for chunk in chunks(delta.upload, config.adb_batch_size):
            send_queue = map(run_cmd, chunk)
            await asyncio.gather(*send_queue)
            progress.update(config.adb_batch_size)


async def touch_files(delta: Delta, chunk: List[FileStat]) -> List[str]:
    """Creates a very long list of adb shell + touch command. should be more efficient"""
    base_adb_command = make_adb_command('shell')
    def generate_cmd(file_stat: FileStat):
        destination = delta.remote_path / file_stat.relname
        return [
            'touch', '-cmd',
            shlex.quote(datetime.fromtimestamp(file_stat.mtime).strftime('%Y-%m-%d%H:%M:%S')),
            shlex.quote(destination.as_posix()),
            ';'
        ]

    adb_command = [*base_adb_command, *chain.from_iterable(map(generate_cmd, chunk))]
    await run_adb_command(adb_command)


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


def mobile_path(s: str) -> bool:
    """
    Checks if path specified points to a phone
    On windows, path can have a drive letter and that adds : to the path.
    To overcome that we only check for `:` that is not the second letter of string,
    where the drive letter colon should always be.
    """
    return s.find(':', 2) != -1

def parse_mobile_path(s: str) -> Tuple[str, str]:
    """
    Attempts to parse a mobile path
    A valid mobile path is [ADB_ID OR 'remote']:path
    """
    i = s.find(':', 2)
    device = s[:i]
    dest_path = s[i + 1:]
    if i == -1 or (device != 'remote' and not device.isnumeric()):
        raise ValueError(f'Invalid mobile path "{s}"')
    return None if device == 'remote' else device, dest_path