#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at https://mozilla.org/MPL/2.0/.
# This code is Copyright 2019 - 2023 Absolute Performance, Inc, and 2024 - 2025
# ProCern Technology Solutions.
# It is written and maintained by Taylor C. Richberger <taylor.richberger@procern.com>

import os

if os.uname().sysname.lower() == 'linux':
    import ctypes
    import ctypes.util

    class inotify_event(ctypes.Structure):
        '''FFI struct for reading inotify events.  Should not be accessed externally.'''
        _fields_ = [
                ("wd", ctypes.c_int),
                ("mask", ctypes.c_uint32),
                ("cookie", ctypes.c_uint32),
                ("len", ctypes.c_uint32),
                # name follows, and is of a variable size
            ]


    def check_return(value: int) -> int:
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
else:
    import warnings
    warnings.warn('inotify is a Linux-only API.  You can package this library on other platforms, but not run it.')
