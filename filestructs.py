import stat
from typing import Dict
from pathlib import Path

from iso8601 import parse_date


class FileStat:
    """
    Base class
    """
    def __init__(self, root, filename, ftype, size, mtime):
        self.filename = filename
        self.relname = root
        self.type = ftype
        self.size = size
        self.mtime = mtime

FileStatDict = Dict[str, FileStat]

class LocalFileStat(FileStat):
    """
    Local filestat
    """
    def __init__(self, root: str, path: Path):
        stat_output = path.stat()
        self.filename = str(path)
        self.relname = path.relative_to(root).as_posix()
        self.type = stat.S_IFMT(stat_output.st_mode)
        self.size = stat_output.st_size
        self.mtime = stat_output.st_mtime

class RemoteFileStat(FileStat):
    """
    Remote filestat from stat command on Linux + some specific flags
    """
    def __init__(self, root, stat_output, delim):
        columns = stat_output.split(delim)
        filebit = int(columns[1], 16)
        self.filename = columns[0]
        self.relname = Path(self.filename).relative_to(root).as_posix()
        self.type = stat.S_IFMT(filebit)
        self.size = int(columns[2])
        self.mtime = parse_date(columns[3]).timestamp()
