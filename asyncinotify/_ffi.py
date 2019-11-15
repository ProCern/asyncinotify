#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2019 Taylor C. Richberger
# This code is released under the license described in the LICENSE file

import ctypes
import os

from .error import InotifyError

libc = ctypes.CDLL("libc.so.6", use_errno=True)

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

class inotify_event(ctypes.Structure) :
    '''FFI struct for reading inotify events.  Should not be accessed externally.'''
    _fields_ = [
            ("wd", ctypes.c_int),
            ("mask", ctypes.c_uint32),
            ("cookie", ctypes.c_uint32),
            ("len", ctypes.c_uint32),
            # name follows, and is of a variable size
        ]

inotify_event_size = ctypes.sizeof(inotify_event)

NAME_MAX = 255
