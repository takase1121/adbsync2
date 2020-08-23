import stat
from typing import Dict
from pathlib import Path

from iso8601 import parse_date

class FilePermission:
    """
    Platform-independent file permission
    """
    def __init__(self, filebit):
        permbit = stat.S_IMODE(filebit)
        self.user = {
            'read'   : bool(permbit & stat.S_IRUSR),
            'write'  : bool(permbit & stat.S_IWUSR),
            'execute': bool(permbit & stat.S_IXUSR)
        }
        self.group = {
            'read'   : bool(permbit & stat.S_IRGRP),
            'write'  : bool(permbit & stat.S_IWGRP),
            'execute': bool(permbit & stat.S_IXGRP)
        }
        self.others = {
            'read'   : bool(permbit & stat.S_IROTH),
            'write'  : bool(permbit & stat.S_IWOTH),
            'execute': bool(permbit & stat.S_IXOTH)
        }


class FileStat:
    """
    Base class
    """
    def __init__(self, root, filename, permissions, ftype, size, mtime):
        self.filename = filename
        self.relname = root
        self.permissions = permissions
        self.type = ftype
        self.size = size
        self.mtime = mtime


FileStatDict = Dict[str, FileStat]
"""
Convenient alias for dict of relname and filestat
"""

class LocalFileStat(FileStat):
    """
    Local filestat
    """
    def __init__(self, root: str, path: Path):
        stat_output = path.stat()
        self.filename = str(path)
        self.relname = path.relative_to(root).as_posix()
        self.permissions = FilePermission(stat_output.st_mode)
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
        self.permissions = FilePermission(filebit)
        self.type = stat.S_IFMT(filebit)
        self.size = int(columns[2])
        self.mtime = parse_date(columns[3]).timestamp()
