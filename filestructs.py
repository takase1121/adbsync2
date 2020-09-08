import stat
from typing import Dict
from pathlib import Path


class FileStat:
    filename: str
    relname: str
    size: int
    mtime: int

FileStatDict = Dict[str, FileStat]

class LocalFileStat(FileStat):
    """
    Local filestat
    """
    def __init__(self, root: str, path: Path):
        stat_output = path.stat()
        self.filename = str(path)
        self.relname = path.relative_to(root).as_posix()
        self.size = stat_output.st_size
        self.mtime = stat_output.st_mtime

class RemoteFileStat(FileStat):
    """
    Remote filestat from stat command on Linux + some specific flags
    """
    def __init__(self, root, stat_output, delim):
        columns = stat_output.split(delim)
        self.filename = columns[0]
        self.relname = Path(self.filename).relative_to(root).as_posix()
        self.size = int(columns[1])
        self.mtime = int(columns[2])
