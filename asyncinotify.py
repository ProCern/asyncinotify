#!/usr/bin/env pysurrogateescapeithon3
# -*- coding: utf-8 -*-
# Copyright © 2019 Taylor C. Richberger
# This code is released under the license described in the LICENSE file

from enum import IntFlag
from io import BytesIO
from pathlib import Path
import asyncio
import ctypes
import os
import weakref

try:
    from asyncio import get_running_loop
except ImportError:
    from asyncio import get_event_loop as get_running_loop

NAME_MAX = 255

libc = ctypes.CDLL("libc.so.6", use_errno=True)

class InotifyError(RuntimeError):
    pass

def check_return(value):
    if value == -1:
        errno = ctypes.get_errno()
        raise InotifyError(f'Call failed, errno {errno}: {os.strerror(errno)}')
    return value

libc.inotify_init.restype = check_return
libc.inotify_init.argtypes = ()
libc.inotify_init1.restype = check_return
libc.inotify_init1.argtypes = (ctypes.c_int,)
libc.inotify_add_watch.restype = check_return
libc.inotify_add_watch.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
libc.inotify_rm_watch.restype = check_return
libc.inotify_rm_watch.argtypes = (ctypes.c_int, ctypes.c_int)

class Mask(IntFlag):
    CLOEXEC = 0x80000
    NONBLOCK = 0x800

    ACCESS = 0x00000001
    MODIFY = 0x00000002
    ATTRIB = 0x00000004
    CLOSE_WRITE = 0x00000008
    CLOSE_NOWRITE = 0x00000010
    CLOSE = CLOSE_WRITE | CLOSE_NOWRITE
    OPEN = 0x00000020
    MOVED_FROM = 0x00000040
    MOVED_TO = 0x00000080
    MOVE = MOVED_FROM | MOVED_TO
    CREATE = 0x00000100
    DELETE = 0x00000200
    DELETE_SELF = 0x00000400
    MOVE_SELF = 0x00000800

    UNMOUNT = 0x00002000
    Q_OVERFLOW = 0x00004000
    IGNORED = 0x00008000

    ONLYDIR = 0x01000000
    DONT_FOLLOW = 0x02000000
    EXCL_UNLINK = 0x04000000
    MASK_ADD = 0x20000000
    ISDIR = 0x40000000
    ONESHOT = 0x80000000

class inotify_event(ctypes.Structure) :
    _fields_ = [
            ("wd", ctypes.c_int),
            ("mask", ctypes.c_uint32),
            ("cookie", ctypes.c_uint32),
            ("len", ctypes.c_uint32),
            # name follows, and is of a variable size
        ]

inotify_event_size = ctypes.sizeof(inotify_event)

class Event(object):

    """Event output class"""

    def __init__(self, watch, mask, cookie, name):
        """Create the class

        :watch: TODO
        :mask: TODO
        :cookie: TODO
        :name: TODO

        """
        if watch:
            self._watch = weakref.ref(watch)
        else:
            self._watch = None

        self._mask = mask
        self._cookie = cookie
        self._name = name
        
    @property
    def watch(self):
        if self._watch is not None:
            return self._watch()

    @property
    def mask(self):
        return self._mask

    @property
    def cookie(self):
        return self._cookie

    @property
    def name(self):
        return self._name

    @property
    def path(self):
        watch = self.watch
        name = self.name
        if watch and name:
            return watch.path / name

    def __repr__(self):
        return f'<Event name={self.name!r} mask={self.mask!r} cookie={self.cookie} watch={self.watch!r}>'

class Watch:
    def __init__(self, inotify, path, mask):
        self._mask = mask
        self._path = path
        self._wd = libc.inotify_add_watch(inotify._fd, str(path).encode('utf-8', 'surrogateescape'), mask)

    @property
    def wd(self):
        return self._wd

    @property
    def path(self):
        return self._path

    @property
    def mask(self):
        return self._mask

    def __repr__(self):
        return f'<Watch path={self.path!r} mask={self.mask!r}>'


class Inotify:
    '''Core Inotify class.'''
    def __init__(self):
        self._fd = libc.inotify_init()

        # Watches dict used for matching events up with the watch descriptor,
        # in order to get the full item path.
        self._watches = {}

    def add_watch(self, path, mask):
        '''Add a watch dir.

        :param path: a string, bytes, or PathLike object
        :param mask: a Mask

        :returns: The relevant Watch instance
        '''

        if isinstance(path, bytes):
            path = path.decode('utf-8', 'surrogateescape')

        if not isinstance(path, os.PathLike):
            path = Path(path)

        watch = Watch(
            inotify=self,
            path=path,
            mask=mask,
        )

        self._watches[watch.wd] = watch

        return watch

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.close()

    def close(self):
        os.close(self._fd)

    # Future get
    def _get(self, future):
        buffer = BytesIO(os.read(self._fd, inotify_event_size + NAME_MAX + 1))
        events = []
        while True:
            event_buffer = buffer.read(inotify_event_size)
            if not event_buffer:
                break
            event_struct = inotify_event.from_buffer_copy(event_buffer)
            length = event_struct.len
            name = None

            if length > 0:
                raw_name = buffer.read(length)
                zero_pos = raw_name.find(0)
                # If zero_pos is 0, we want name to stay None
                if zero_pos != 0:
                    # If zero_pos is -1, we want the whole name string, otherwise truncate the zeros
                    if zero_pos > 0:
                        raw_name = raw_name[:zero_pos]
                    name = Path(raw_name.decode('utf-8', 'surrogateescape'))

            event = Event(
                # wd may be -1
                watch=self._watches.get(event_struct.wd),
                mask=Mask(event_struct.mask),
                cookie=event_struct.cookie,
                name=name,
            )
            events.append(event)

        future.set_result(events)

    async def get(self):
        event_loop = get_running_loop()
        future = event_loop.create_future()
        event_loop.add_reader(self._fd, self._get, future)
        result = await future
        event_loop.remove_reader(self._fd)
        return result

    def __aiter__(self):
        return self

    async def __anext__(self):
        '''Iterate notify events forever.'''
        return await self.get()
