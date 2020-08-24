#!/usr/bin/env python3

import asyncio
import argparse
from os import linesep
from functools import reduce
from typing import Union

import config
import sync
from filestructs import FileStat


def get_args():
    """Get arguments from command line"""
    parser = argparse.ArgumentParser(description='Rsync like thingy')
    parser.add_argument('--device', required=False,
                        default=None, dest='device',
                        help='Device ID for adb')

    parser.add_argument('--dry-run', required=False,
                        action='store_true', default=False, dest='dry_run',
                        help='Does not do anything on the destination filesystem')

    parser.add_argument('--debug', required=False,
                        action='store_true', default=False, dest='debug',
                        help='Shows more info about current progress. Literally a ton of them')
    
    parser.add_argument('--debug-stat', required=False,
                        action='store_true', default=False, dest='debug_stat',
                        help='Shows stat command generated. This will REALLY bloat the console output.')

    parser.add_argument('--dump-delta', required=False,
                        default=None, metavar='DELTA_PATH', dest='delta_path',
                        help='If a filename is specified, the delta is dumped into the file as JSON')

    parser.add_argument('--max-depth', required=False,
                        type=int, default=10, dest='max_depth',
                        help='Max depth for both local and remote')

    parser.add_argument('--delete', required=False,
                        action='store_true', default=False, dest='delete_files',
                        help='Creates a "perfect mirror" of local at remote')
 
    parser.add_argument('source', help='The source')
    parser.add_argument('destination', help='The destination')
    return parser.parse_args()


def accumulate(a: Union[str, FileStat], b: FileStat) -> int:
    return a.size + b.size if isinstance(a, FileStat) else a + b.size


async def run(args):
    """Runs everything"""
    diff = await sync.get_diff(
        args.source, args.destination,
        max_depth=args.max_depth, delete_files=args.delete_files,
        delta_path=args.delta_path)

    if args.delete_files and len(diff.delete) > 0:
        await sync.del_remote(diff)
    else:
        print('[Main] No files to delete, hooray!')

    if len(diff.add) > 0:
        await sync.send_remote(diff)
    else:
        print('[Main] No files to send to remote, hooray!')

    total_transferred = reduce(accumulate, diff.add.values(), 0)
    total_deleted = reduce(accumulate, diff.delete.values(), 0)
    print(linesep * 2)
    print(f'Transfer completed! {total_transferred} byte(s) transferred, {total_deleted} byte(s) deleted.')
    print(f'Deleted {len(diff.delete)} file(s) and sent {len(diff.add)} file(s).')
    print('Have a nice day and may I never need to fix this again.')

def main():
    """Runs the thing that runs everything"""
    args = get_args()
    config.debug_general = args.debug
    config.debug_stat = args.debug_stat
    config.dry_run = args.dry_run
    config.device = args.device
    
    asyncio.run(run(args))