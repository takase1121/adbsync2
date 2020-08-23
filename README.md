# adbsync2

This a ripoff of Google's [adb-sync](https://github.com/google/adb-sync). I don't like typing dashes in between names so I remove the dash and added 2 at the back. In reality, its has only 25% functionality of `adb-sync`. This is also my first Python project.

### Dependencies
##### Local machine:
- `adb`
- `adb` drivers installed
- `python ~= 3.8.5`

##### Remote machine:
- `adbd` (Just enable USB Debugging in Developer options)
- `find` (At least supports `-maxdepth` and `-type`)
- `stat` (At least support custom format string. For the actual format string check thee source code)
- Faith in me that I won't break your phone with this script

### Algorithm
0. If remote has file but local don't and `--delete` is specified `->` Delete file
1. If local has file but remote don't `->` Send file
2. If both has file but size are different `->` Send file
3. If both has file but local mtime `>` remote mtime `->` Send file

There is no complex stuff going under the hood - not even hashing.

### Tested to work
my Redmi 7A.