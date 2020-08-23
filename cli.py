#!/usr/bin/env python3

import asyncio
import argparse
from os import linesep
from functools import reduce

import config
import sync

def get_args():
    parser = argparse.ArgumentParser(description='Rsync like thingy')
    parser.add_argument('--device', required=False,
                        default=None,
                        help='Device ID for adb')

    parser.add_argument('--dry-run', required=False,
                        action='store_true', default=False, dest='dry_run',
                        help='Does not do anything on the destination filesystem')

    parser.add_argument('--debug', required=False,
                        action='store_true', default=False,
                        help='Shows more info about current progress. Literally a ton of them')
    
    parser.add_argument('--debug-stat', required=False,
                        action='store_true', default=False, dest='debug_stat',
                        help='Shows stat command generated. This will REALLY bloat the console output.')

    parser.add_argument('--dump-delta', required=False,
                        default=None, metavar='DELTA_PATH', dest='delta_path',
                        help='If a filename is specified, the delta is dumped into the file as JSON')

    parser.add_argument('--max-depth', required=False,
                        type=int, default=10, dest='depth',
                        help='Max depth for both local and remote')

    parser.add_argument('--delete', required=False,
                        action='store_true', default=False,
                        help='Creates a "perfect mirror" of local at remote')
 
    parser.add_argument('source', help='The source')
    parser.add_argument('destination', help='The destination')
    return parser.parse_args()


async def run(args):
    diff = await sync.get_diff(args.source, args.destination,
                            depth=args.depth, find_delete=args.delete,
                            dry_run=args.dry_run, dump_delta=args.delta_path)
    if args.delete and len(diff.delete) > 0:
        await sync.del_remote(diff, dry_run=args.dry_run)
    else:
        print('[Main] No files to delete, hooray!')

    if len(diff.add) > 0:
        await sync.send_remote(diff, dry_run=args.dry_run)
    else:
        print('[Main] No files to send to remote, hooray!')

    accumulate = lambda a, b: (a if isinstance(a, int) else a.size) + b.size
    total_transferred = reduce(accumulate, diff.add.values(), 0)
    total_deleted = reduce(accumulate, diff.delete.values(), 0)
    print(linesep * 2)
    print(f'Transfer completed! {total_transferred} byte(s) transferred, {total_deleted} byte(s) deleted.')
    print(f'Deleted {len(diff.delete)} file(s) and sent {len(diff.add)} file(s).')
    print(f'Have a nice day and may I never need to fix this again.')

def realmain():
    args = get_args()
    config.is_debug = args.debug
    config.device = args.device
    config.debug_stat = args.debug_stat
    
    asyncio.run(run(args))