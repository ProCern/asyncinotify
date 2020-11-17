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

from ._ffi import libc, inotify_event, inotify_event_size, NAME_MAX

class InitFlags(IntFlag):
    '''Init flags for use with the :class:`Inotify` constructor.

    You shouldn't have a reason to use this, as :attr:`CLOEXEC` will be desired
    because there's no reason for exec'd children to inherit inotify handles
    here, and :attr:`NONBLOCK` shouldn't even make a difference due to the
    handle always being watched with select.
    '''

    #: Set the close-on-exec (FD_CLOEXEC) flag on the new file descriptor.  See
    #: the description of the O_CLOEXEC flag in  open(2)  for  reasons why this
    #: may be useful.
    CLOEXEC = 0x80000

    #: Set the O_NONBLOCK file status flag on the open file description (see
    #: open(2)) referred to by the new file descriptor.  Using this flag saves
    #: extra calls to fcntl(2) to achieve the same result.
    NONBLOCK = 0x800

class Mask(IntFlag):
    '''Bit-mask for adding a watch and for analyzing watch events.

    Because this is an IntFlag, all IntFlag operations work on it, such as
    using the bitwise or operator to combine, or using the `in` operator to
    check contents.
    '''

    #: File was accessed (e.g., read(2), execve(2)).
    ACCESS = 0x00000001

    #: File was modified (e.g., write(2), truncate(2)).
    MODIFY = 0x00000002

    #: Metadata changed—for example, permissions (e.g., chmod(2)), timestamps
    #: (e.g.,  utimensat(2)),  extended  attributes  (setxattr(2)),  link count
    #: (since Linux 2.6.25; e.g., for the target of link(2) and for unlink(2)),
    #: and user/group ID (e.g., chown(2)).
    ATTRIB = 0x00000004

    #: File opened for writing was closed.
    CLOSE_WRITE = 0x00000008

    #: File or directory not opened for writing was closed.
    CLOSE_NOWRITE = 0x00000010

    #: :attr:`CLOSE_WRITE` | :attr:`CLOSE_NOWRITE`
    CLOSE = CLOSE_WRITE | CLOSE_NOWRITE

    #: File or directory was opened.
    OPEN = 0x00000020

    #: Generated for the directory containing the old filename when a file is renamed.
    #: Note the cookie member in :class:`Event`.
    MOVED_FROM = 0x00000040

    #: Generated for the directory containing the new filename when a file is renamed.
    #: Note the cookie member in :class:`Event`.
    MOVED_TO = 0x00000080

    #: :attr:`MOVED_FROM: | :attr:`MOVED_TO`
    MOVE = MOVED_FROM | MOVED_TO

    #: File/directory created in watched directory (e.g., open(2) O_CREAT,
    #: mkdir(2), link(2), symlink(2), bind(2) on a UNIX domain socket).
    CREATE = 0x00000100

    #: File/directory deleted from watched directory.
    DELETE = 0x00000200

    #: Watched  file/directory  was  itself deleted.  (This event also occurs
    #: if an object is moved to another filesystem, since mv(1) in effect
    #: copies the file to the other filesystem and then deletes it from the
    #: original filesystem.)  In addition, an :attr:`Mask.IGNORED` event will
    #: subsequently be generated for the watch descriptor.
    DELETE_SELF = 0x00000400

    #: Watched file/directory was itself moved.
    MOVE_SELF = 0x00000800

    #: Filesystem containing watched object was unmounted.  In addition, an
    #: :attr:`Mask.IGNORED` event  will  subsequently  be  generated  for  the  watch
    #: descriptor.
    UNMOUNT = 0x00002000

    #: Event queue overflowed (wd is -1 for this event (:meth:`Event.watch` will be None)).
    Q_OVERFLOW = 0x00004000

    #: Watch was removed explicitly (inotify_rm_watch(2)) or automatically
    #: (file was deleted, or filesystem was unmounted).
    IGNORED = 0x00008000

    #: (since Linux 2.6.15)
    #: Watch pathname only if it is a directory; the error ENOTDIR results if
    #: pathname is not a directory.  Using this flag provides an application
    #: with a race-free way of ensuring that the monitored object is a
    #: directory.
    ONLYDIR = 0x01000000

    #: Don't dereference pathname if it is a symbolic link.
    DONT_FOLLOW = 0x02000000

    #: By  default,  when  watching  events on the children of a directory,
    #: events are generated for children even after they have been unlinked
    #: from the directory.  This can result in large numbers of uninteresting
    #: events for some applications (e.g., if  watching  /tmp,  in  which many
    #: applications create temporary files whose names are immediately
    #: unlinked).  Specifying :attr:`Mask.EXCL_UNLINK` changes the default behavior, so
    #: that events are not generated for children after they have been unlinked
    #: from the watched directory.
    EXCL_UNLINK = 0x04000000

    #: (since Linux 4.18)
    #: Watch pathname only if it does not already have a watch associated with
    #: it; the  error  EEXIST  results  if  pathname  is  already  being
    #: watched.  Using this flag provides an application with a way of ensuring
    #: that new watches do not modify existing ones.  This is useful because
    #: multiple paths may refer to the same inode, and multiple calls to
    #: inotify_add_watch(2) without this flag may clobber existing watch masks.
    MASK_CREATE = 0x10000000

    #: If a watch instance already exists for the filesystem object
    #: corresponding to pathname, add (OR) the events in mask  to  the  watch
    #: mask (instead of replacing the mask); the error EINVAL results if
    #: :attr:`Mask.MASK_CREATE` is also specified.
    MASK_ADD = 0x20000000

    #: Subject of this event is a directory.
    ISDIR = 0x40000000

    #: Monitor the filesystem object corresponding to pathname for one event,
    #: then remove from watch list.
    ONESHOT = 0x80000000

class Event:
    '''Event output class.

    The :class:`Mask` values may be tested directly against this class.
    '''

    def __init__(self, watch, mask, cookie, name):
        """Create the class.  This class is internal, for all intents and
        purposes.  Client code should have no reason to construct instances of
        it.

        :watch: A :class:`Watch` instance, a weakref, or None
        :mask: The mask that this event was created with
        :cookie: The cookie integer for identifying move operations
        :name: The name path.
        :owns_watch: Whether the event should own the watch.
        """

        self._mask = mask
        self._cookie = cookie
        self._name = name
        self._watch = watch
        
    @property
    def watch(self):
        '''The actual Watch instance associated with this event.
        
        This is stored internally as a weak reference.  If the event is taken
        out of context and outlives its generating :class:`Inotify`, this may
        return None.

        If :meth:`mask` contains IGNORED or the watch was a ONESHOT, this is
        not a weak reference, but the actual watch instance.  If the watch was
        ONESHOT, the corresponding IGNORED will not have a watch instance, only
        the ONESHOT event itself.  This may be inconvenient, but the inotify
        man page doesn't give strong enough guarantees to risk memory leak with
        ONESHOT events by leaving the ownership change exclusively to IGNORED
        events.

        :returns: the watch instance that generated this
        :rtype: Watch
        '''

        if self._watch is None or isinstance(self._watch, Watch):
            return self._watch
        else:
            return self._watch()

    @property
    def mask(self):
        '''The mask associated with this event
        
        :returns: the mask for this event
        :rtype: Mask
        '''
        return self._mask

    @property
    def cookie(self):
        '''The cookie associated with this event.

        According to the `inotify man page
        <http://man7.org/linux/man-pages/man7/inotify.7.html>`_, cookie is a
        unique integer that connects related events.  Currently, this is used
        only for rename events, and allows the resulting pair of :attr:`Mask.MOVED_FROM`
        and :attr:`Mask.MOVED_TO` events to be connected by the application.  For all
        other event types, cookie is set to 0.
        
        :returns: the cookie for this event
        :rtype: int
        '''
        return self._cookie

    @property
    def name(self):
        '''The name associated with the event.
        May be None, indicating the watch directory itself.

        :returns: the name of the event, or None if the event is for the watch itself
        :rtype: pathlib.Path
        '''
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

        :returns: the full path for the event, or None if it can not be constructed.
        :rtype: pathlib.Path
        '''
        watch = self.watch
        name = self.name
        if watch is not None:
            if name:
                return watch.path / name
            else:
                return watch.path

    def __contains__(self, value):
        if isinstance(value, Mask):
            return value in self.mask
        raise TypeError("Only Mask is supported with Event's 'in' operator")

    def __repr__(self):
        return f'<Event name={self.name!r} mask={self.mask!r} cookie={self.cookie} watch={self.watch!r}>'

class Watch:
    '''Watch class.

    You usually won't construct this directly, but rather use
    :meth:`Inotify.add_watch` to create it.
    '''
    def __init__(self, inotify, path, mask, wd):
        '''
        Do not instantiate this directly.  Use :meth:`Inotify.add_watch` instead.

        :param Inotify inotify: The :class:`Inotify` instance this Watch is being added to
        :param pathlib.Path path: A :class:`pathlib.Path` to the watch destination
        :param Mask mask: The mask for the added watch.
        '''
        self._inotify = weakref.ref(inotify)
        self._mask = mask
        self.path = path
        self._wd = wd

    @property
    def inotify(self):
        '''The :class:`Inotify` instance this Watch belongs to.

        This is internally stored as a weakref, so if the :class:`Watch`
        outlives the :class:`Inotify`, this may return None.

        :returns: The :class:`Inotify` instance this Watch belongs to.
        :rtype: Inotify
        '''
        return self._inotify()

    @property
    def wd(self):
        '''
        :returns: the raw watch descriptor
        :rtype: int
        '''
        return self._wd

    @property
    def path(self):
        '''
        :returns: The path that this watch is for
        :rtype: pathlib.Path
        '''
        return self._path

    @path.setter
    def path(self, value):
        self._path = Path(value)

    @property
    def mask(self):
        '''
        :returns: The mask that was used to construct this watch
        :rtype: Mask
        '''
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

        wd = libc.inotify_add_watch(self._fd, str(path).encode('utf-8', 'surrogateescape'), mask)

        # Happens for things like an existing watch instance being modified,
        # like MASK_ADD
        if wd in self._watches:
            watch = self._watches[wd]
        else:
            watch = Watch(
                inotify=self,
                path=path,
                mask=mask,
                wd=wd,
            )
            self._watches[wd] = watch

        return watch

    def rm_watch(self, watch):
        '''Remove a watch from this inotify instance.

        This will generate an :attr:`Mask.IGNORED` event that contains the :class:`Watch`
        instance.

        :param Watch watch: the :class:`Watch` to remove
        '''

        libc.inotify_rm_watch(self._fd, watch.wd)

        # This does not remove from self._watches because the IGNORE event will
        # do that for you.

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.close()

    def __del__(self):
        self.close()

    def close(self):
        '''Close the file descriptor for this inotify.

        Once this is done, do not do anything more with this inotify instance.
        Associated :class:`Watch` and :class:`Event` instances are still valid,
        but no more may be created, and if this :class:`Inotify` goes out of
        scope and is cleaned up, the :class:`Event` may lose its
        :class:`Watch` if you don't have a reference to it.

        This is automatically called when this class is used as a context
        manager.
        '''
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    @property
    def cache_size(self):
        '''The maximum number of full-sized events (events with a NAME_MAX-length name) to store.

        More events may be stored, because very few events should use a NAME_MAX length name.'''
        return self._cache_size

    @cache_size.setter
    def cache_size(self, value):
        self._cache_size = int(value)

    def _get(self, future):
        '''Retrieve an array of events into an array, which is set on the passed-in future.'''

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

            watch = self._watches.get(event_struct.wd, None)

            if watch is not None:
                if Mask.IGNORED in mask or Mask.ONESHOT in watch.mask:
                    # If IGNORED or ONESHOT, the event takes ownership of this watch
                    del self._watches[event_struct.wd]
                elif watch is not None:
                    # Otherwise, Initify retains ownership and a weak reference is created
                    watch = weakref.ref(watch)

            event = Event(
                watch=watch,
                mask=mask,
                cookie=event_struct.cookie,
                name=name,
            )
            events.append(event)


        future.set_result(events)

    async def get(self):
        '''Get a single next event.

        This is the core method of event retrieval.  Asynchronously iterating
        this class simply calls this method forever.

        May actually pull multiple events from the inotify handle, and store
        extras internally.  Will always only return one.

        Building some events may cause changes in the associated
        :class:`Inotify` or :class:`Watch` instances.  For instance,
        :attr:`Mask.IGNORE` will automatically remove its :class:`Watch`
        instance from this :class:`Inotify` object.  A :attr:`Mask.ONESHOT`
        Watch will remove itself on the first event.

        .. caution::

            A watched path being moved will cause the relevant
            :meth:`Watch.path` to be incorrect.  This library will not
            automatically update it for you, because :attr:`Mask.MOVE_SELF`
            does not tell you the new name.  You would have to watch the parent
            directory and change the :meth:`Watch.path` value yourself if you
            want that functionality.

            If you don't do this and the watch path is moved, the
            :class:`Event` will have a correct name but incorrect path.

        :returns: a single :class:`Event`
        :rtype: Event
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
        '''Iterate inotify events forever with :meth:`get`.'''
        return await self.get()
