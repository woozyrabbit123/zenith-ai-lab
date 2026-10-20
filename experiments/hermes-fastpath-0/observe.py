"""Independent Linux filesystem observation; imports no recipe or Hermes code."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct

CONTRACT_HASH = 'd1905319d7b20814ca0c1d0fb25e3592a9bdec829483ac01e46179a7dcc92fa5'


def contract(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONTRACT_HASH:
        raise ValueError('Frozen acceptance contract changed')
    return json.loads(raw)


class Writes:
    """Count actual atomic replacements of the named settings file via the kernel."""
    def __init__(self, root):
        libc = ctypes.CDLL(None, use_errno=True)
        libc.inotify_init1.argtypes, libc.inotify_init1.restype = [ctypes.c_int], ctypes.c_int
        libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        libc.inotify_add_watch.restype = ctypes.c_int
        self.fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), 'inotify unavailable')
        self.watches = {}
        for directory in (root, root/'.fastpath'):
            watch = libc.inotify_add_watch(self.fd, os.fsencode(directory), 0x80 | 0x100 | 0x200 | 0x2)
            if watch < 0:
                os.close(self.fd)
                raise OSError(ctypes.get_errno(), 'inotify watch unavailable')
            self.watches[watch] = '.' if directory == root else '.fastpath'

    def finish(self):
        events = []
        try:
            while True:
                try:
                    data = os.read(self.fd, 65536)
                except BlockingIOError:
                    break
                offset = 0
                while offset < len(data):
                    watch, mask, cookie, length = struct.unpack_from('iIII', data, offset)
                    name = data[offset+16:offset+16+length].split(b'\0', 1)[0].decode()
                    if mask & 0x4000:
                        raise RuntimeError('inotify overflow; write count invalid')
                    events.append({'directory': self.watches.get(watch), 'mask': mask, 'name': name})
                    offset += 16 + length
        finally:
            os.close(self.fd)
        return events


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and '.git' not in p.relative_to(root).parts}


def safe_snapshot(files):
    return {k: {'sha256': hashlib.sha256(v).hexdigest(), 'bytes': len(v), 'content': v.decode()}
            for k, v in files.items()}
