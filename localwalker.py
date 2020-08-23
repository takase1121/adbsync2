from typing import Dict
from pathlib import Path

from tqdm import tqdm

from filestructs import LocalFileStat, FileStatDict


def not_max_depth(path: Path, root: Path, depth: int):
    """
    Return true if depth of current path is less then max depth specified.
    """
    return len(path.relative_to(root).parents) <= depth


async def get_local_files(path: str, max_depth:int=1,
                    output_dict:FileStatDict={}) -> FileStatDict:
    """
    Get a tree structure of files in the path
    given the specified depth.
    """
    p = Path(path)

    print()
    for file in tqdm([f for f in p.rglob('*') if f.is_file() and not_max_depth(f, p, max_depth)],
                    desc='[LocalWalker] Generating local file list'):
        stat = LocalFileStat(path, file)
        output_dict[stat.relname] = stat
    return output_dict
