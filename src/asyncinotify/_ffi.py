#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2019 Taylor C. Richberger
# This code is released under the license described in the LICENSE file

import ctypes
import ctypes.util
import os

class inotify_event(ctypes.Structure):
    '''FFI struct for reading inotify events.  Should not be accessed externally.'''
    _fields_ = [
            ("wd", ctypes.c_int),
            ("mask", ctypes.c_uint32),
            ("cookie", ctypes.c_uint32),
            ("len", ctypes.c_uint32),
            # name follows, and is of a variable size
        ]


def check_return(value: ctypes.c_int) -> ctypes.c_int:
    if value == -1:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))

    return value


inotify_event_size = ctypes.sizeof(inotify_event)
NAME_MAX = 255

# May be None, which will work fine anyway if the program is linked dynamically
# against an appropriate libc.
_libcname = ctypes.util.find_library('c')
libc = ctypes.CDLL(_libcname, use_errno=True)

libc.inotify_init.restype = check_return
libc.inotify_init.argtypes = ()
libc.inotify_init1.restype = check_return
libc.inotify_init1.argtypes = (ctypes.c_int,)
libc.inotify_add_watch.restype = check_return
libc.inotify_add_watch.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
libc.inotify_rm_watch.restype = check_return
libc.inotify_rm_watch.argtypes = (ctypes.c_int, ctypes.c_int)
