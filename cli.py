#!/usr/bin/env python3

import asyncio
import logging
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
    parser.add_argument('--dry-run', required=False,
                        action='store_true', default=False, dest='dry_run',
                        help='Does not do anything on the destination filesystem')

    parser.add_argument('-v', '--verbose', required=False,
                        action='count', default=0, dest='vlevel',
                        help='Log level')

    parser.add_argument('--dump-delta', required=False,
                        default=None, metavar='DELTA_PATH', dest='delta_path',
                        help='If a filename is specified, the delta is dumped into the file as JSON')

    parser.add_argument('--max-depth', required=False,
                        type=int, default=10, dest='max_depth',
                        help='Max depth for both local and remote')

    parser.add_argument('--adb-batch-size', required=False,
                        type=int, default=5, dest='adb_batch_size',
                        help='Maximum number of adb push to run in parallel')

    parser.add_argument('--command-batch-size', required=False,
                        type=int, default=100, dest='command_batch_size',
                        help='Maximum number of arguments / chained commands to run at once')

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
    diff = None
    try:
        diff = await sync.get_diff(
            args.source, args.destination,
            max_depth=args.max_depth, delete_files=args.delete_files,
            delta_path=args.delta_path)
    except BaseException as e:
        logging.error(e)
        return

    if args.delete_files and len(diff.remove) > 0:
        (await sync.del_remote(diff)
            if diff.direction == sync.SyncDirection.MACHINE_TO_PHONE else
        await sync.del_local(diff))
    else:
        logging.info('No files to delete, hooray!')

    if len(diff.upload) > 0:
        (await sync.send_to_remote(diff)
            if diff.direction == sync.SyncDirection.MACHINE_TO_PHONE else
        await sync.send_to_local(diff))
    else:
        logging.info('No files to send to remote, hooray!')

    total_transferred = reduce(accumulate, diff.upload, 0)
    total_deleted = reduce(accumulate, diff.remove, 0)
    print(linesep * 2)
    logging.info(f'Transfer completed! {total_transferred} byte(s) transferred, {total_deleted} byte(s) deleted.')
    logging.info(f'Deleted {len(diff.remove)} file(s) and sent {len(diff.upload)} file(s).')

def main():
    """Runs the thing that runs everything"""
    args = get_args()

    levels = [logging.INFO, logging.DEBUG]
    level = levels[min(len(levels) - 1, args.vlevel)]
    logging.basicConfig(level=level)

    config.dry_run = args.dry_run
    config.adb_batch_size = args.adb_batch_size
    config.command_batch_size = args.command_batch_size
    
    asyncio.run(run(args))