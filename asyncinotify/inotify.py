#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2019 Taylor C. Richberger
# This code is released under the license described in the LICENSE file

from enum import IntFlag
from io import BytesIO
from pathlib import Path
import asyncio
import os
import weakref

# Python 3.7 suggests get_running_loop for library code
try:
    from asyncio import get_running_loop
except ImportError:
    from asyncio import get_event_loop as get_running_loop

from .ffi import libc, inotify_event, inotify_event_size, NAME_MAX

class InitFlags(IntFlag):
    '''Init flags for use with the :class:`Inotify` constructor.

    You shouldn't have a reason to use this, as CLOEXEC will be desired because
    there's no reason for exec'd children to inherit inotify handles here, and
    NONBLOCK shouldn't even make a difference due to the handle always being
    watched with select.
    '''

    CLOEXEC = 0x80000
    NONBLOCK = 0x800

class Mask(IntFlag):
    '''Bit-mask for adding a watch and for analyzing watch events.

    Because this is an IntFlag, all IntFlag operations work on it, such as
    using the bitwise or operator to combine, or using the `in` operator to
    check contents.
    '''
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

class Event:
    '''Event output class'''

    def __init__(self, watch, mask, cookie, name):
        """Create the class.  This class is internal, for all intents and
        purposes.  Client code should have no reason to construct instances of
        it.

        :watch: A :class:`Watch` instance, or none
        :mask: The mask that this event was created with
        :cookie: The cookie integer for identifying move operations
        :name: The name path.
        """

        self._mask = mask
        self._cookie = cookie
        self._name = name

        if Mask.IGNORED in self.mask:
            self._watch = watch
        else:
            if watch:
                self._watch = weakref.ref(watch)
            else:
                self._watch = None

        
    @property
    def watch(self):
        '''The actual Watch instance associated with this event.
        
        This is stored internally as a weak reference.  If the event is taken
        out of context and outlives its generating :class:`Inotify`, this may
        return None.

        If :meth:`mask` contains IGNORED, this is not a weak reference, but the
        actual watch instance.
        '''
        if self._watch is not None:
            if Mask.IGNORED in self.mask:
                return self._watch
            else:
                return self._watch()

    @property
    def mask(self):
        return self._mask

    @property
    def cookie(self):
        return self._cookie

    @property
    def name(self):
        '''The name associated with the event.
        May be None, indicating the watch directory itself.'''
        return self._name

    @property
    def path(self):
        '''The full path to this event, constructed from the :class:`Watch`
        path and the :meth:`name`.

        If the :class:`Watch` no longer exists, this returns None.  If the
        :meth:`name` does not exist, just returns the watch path.  This value
        is absolute if the path used to construct the :class:`Watch` (the path
        used with :meth:`Inotify.add_watch`) is absolute, otherwise it is
        relative.  This means if you have changed directory between
        constructing a watch with a relative path and receiving this event, you
        will have to have another way of identifying the file correctly.
        '''
        watch = self.watch
        name = self.name
        if watch:
            if name:
                return watch.path / name
            else:
                return watch.path

    def __repr__(self):
        return f'<Event name={self.name!r} mask={self.mask!r} cookie={self.cookie} watch={self.watch!r}>'

class Watch:
    '''Watch class.

    You usually won't construct this directly, but rather use
    :meth:`Inotify.add_watch` to create it.
    '''
    def __init__(self, inotify, path, mask):
        '''
        Do not instantiate this directly.  Use :meth:`Inotify.add_watch` instead.

        :param Inotify inotify: The :class:`Inotify` instance this Watch is being added to
        :param pathlib.Path path: A :class:`pathlib.Path` to the watch destination
        :param Mask mask: The mask for the added watch.
        '''
        self._inotify = weakref.ref(inotify)
        self._mask = mask
        self._path = path
        self._wd = libc.inotify_add_watch(inotify._fd, str(path).encode('utf-8', 'surrogateescape'), mask)

    @property
    def inotify(self):
        '''The :class:`Inotify` instance this Watch belongs to.

        This is internally stored as a weakref, so if the :class:`Watch`
        outlives the :class:`Inotify`, this may return None.
        '''
        return self._inotify()

    @property
    def wd(self):
        '''The raw watch descriptor'''
        return self._wd

    @property
    def path(self):
        '''The :class:`pathlib.Path` that this watch is for'''
        return self._path

    @property
    def mask(self):
        '''The :class:`Mask` that was used to construct this watch'''
        return self._mask

    def __repr__(self):
        return f'<Watch path={self.path!r} mask={self.mask!r}>'


class Inotify:
    '''Core Inotify class.

    Fetches events in bulk, if possible, and stores them internally.

    Use :meth:`get` to get a single event.  This class operates as an async
    generator, and may be asynchronously iterated, and will return events
    forever.

    :param int cache_size: The max number of full-size events to cache.  The
        actual number may be higher, because most events will not be
        full-sized.
    '''
    def __init__(self, flags=InitFlags.CLOEXEC | InitFlags.NONBLOCK, cache_size=10):
        self.cache_size = cache_size
        self._fd = libc.inotify_init()

        # Watches dict used for matching events up with the watch descriptor,
        # in order to get the full item path.
        self._watches = {}

        self._events = None

    def add_watch(self, path, mask):
        '''Add a watch dir.

        :param pathlib.Path path: a string, bytes, or PathLike object
        :param Mask mask: a Mask determining how the watch behaves

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

    def rm_watch(self, watch):
        '''Remove a watch from this inotify instance.

        This will generate an IN_IGNORED event that contains the :class:`Watch`
        instance.

        :param Watch watch: the :class:`Watch` to remove
        '''

        libc.inotify_rm_watch(self._fd, watch.wd)

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.close()

    def close(self):
        os.close(self._fd)

    @property
    def cache_size(self):
        '''The maximum number of full-sized events (events with a NAME_MAX-length name) to store.

        More events may be stored, because very few events should use a NAME_MAX length name.'''
        return self._cache_size

    @cache_size.setter
    def cache_size(self, value):
        self._cache_size = int(value)

    def _get(self, future):
        buffer = BytesIO(os.read(self._fd, (inotify_event_size + NAME_MAX + 1) * self._cache_size))
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
            mask = Mask(event_struct.mask)

            # If IGNORED, the event takes ownership of this watch
            if Mask.IGNORED in mask:
                watch = self._watches.pop(event_struct.wd, None)
            else:
                watch = self._watches.get(event_struct.wd)

            event = Event(
                # wd may be -1
                watch=watch,
                mask=mask,
                cookie=event_struct.cookie,
                name=name,
            )
            events.append(event)

        future.set_result(events)

    async def get(self):
        '''Get a single next event.

        May actually pull multiple events from the inotify handle, and store
        extras internally.  Will always only return one.
        '''
        if not self._events:
            event_loop = get_running_loop()
            future = event_loop.create_future()
            event_loop.add_reader(self._fd, self._get, future)
            self._events = await future
            event_loop.remove_reader(self._fd)
        return self._events.pop(0)

    def __aiter__(self):
        return self

    async def __anext__(self):
        '''Iterate notify events forever.'''
        return await self.get()
