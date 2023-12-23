#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2019 Taylor C. Richberger
# This code is released under the license described in the LICENSE file

import sys

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from asyncinotify import Event, Inotify, Mask

if sys.version_info > (3, 8):
    from collections.abc import Sequence
else:
    from typing import Sequence

import asyncio
try:
    from asyncio import run
    from asyncio import create_task
except ImportError:
    from asyncio import ensure_future as create_task
    def run(main): # type: ignore
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            try:
                return loop.run_until_complete(main)
            finally:
                loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()

class TestInotify(unittest.TestCase):

    async def watch_events(self) -> Sequence[Event]:
        '''Watch events until an IGNORED is received for the main watch, then
        return the events.'''
        events = []
        with self.inotify as inotify:
            async for event in inotify:
                events.append(event)
                if Mask.IGNORED in event and event.watch is self.watch:
                    return events

        raise RuntimeError()

    def gather_events(self, function) -> Sequence[Event]:
        '''Run the function "soon" in the event loop, and also watch events
        until you can return the result.'''

        try:
            function()
        finally:
            self.inotify.rm_watch(self.watch)

        return run(self.watch_events())

    def setUp(self):
        self._dir = TemporaryDirectory()
        self.dir = Path(self._dir.name)
        self.inotify = Inotify()
        self.watch = self.inotify.add_watch(self.dir, Mask.ACCESS | Mask.MODIFY | Mask.ATTRIB | Mask.CLOSE_WRITE | Mask.CLOSE_NOWRITE | Mask.OPEN | Mask.MOVED_FROM | Mask.MOVED_TO | Mask.CREATE | Mask.DELETE | Mask.DELETE_SELF | Mask.MOVE_SELF)

    def tearDown(self):
        self._dir.cleanup()

    def test_diriterated(self):
        def test():
            list(self.dir.iterdir())

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.ISDIR|Mask.OPEN in event and event.path == self.dir for event in events))
        self.assertTrue(any(Mask.ISDIR|Mask.ACCESS in event and event.path == self.dir for event in events))
        self.assertTrue(any(Mask.ISDIR|Mask.CLOSE_NOWRITE in event and event.path == self.dir for event in events))
        self.assertTrue(any(Mask.IGNORED in event and event.path == self.dir for event in events))

    def test_foo_opened_and_closed(self):
        def test():
            with open(self.dir / 'foo', 'w'):
                pass
            with open(self.dir / 'foo', 'r'):
                pass

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.CREATE in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.OPEN in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.CLOSE_WRITE in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.CLOSE_NOWRITE in event and event.path == self.dir / 'foo' for event in events))

    def test_foo_deleted(self):
        def test():
            with open(self.dir / 'foo', 'w'):
                pass

            (self.dir / 'foo').unlink()

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.DELETE in event and event.path == self.dir / 'foo' for event in events))

    def test_foo_write(self):
        def test():
            with open(self.dir / 'foo', 'w') as file:
                file.write('test')

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.CREATE in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.OPEN in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.MODIFY in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.CLOSE_WRITE in event and event.path == self.dir / 'foo' for event in events))

    def test_foo_moved(self):
        def test():
            with open(self.dir / 'foo', 'w'):
                pass

            (self.dir / 'foo').rename(self.dir / 'bar')

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.MOVED_FROM in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.MOVED_TO in event and event.path == self.dir / 'bar' for event in events))
        self.assertEqual(
            next(event.cookie for event in events if Mask.MOVED_FROM in event),
            next(event.cookie for event in events if Mask.MOVED_TO in event),
        )

    def test_foo_attrib(self):
        def test():
            with open(self.dir / 'foo', 'w'):
                pass

            (self.dir / 'foo').chmod(0o777)

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.ATTRIB in event and event.path == self.dir / 'foo' for event in events))

    def test_onlydir_error(self):
        with open(self.dir / 'foo', 'w'):
            pass

        # Will not raise error
        self.inotify.add_watch(self.dir / 'foo', Mask.ATTRIB)

        with self.assertRaises(OSError):
            self.inotify.add_watch(self.dir / 'foo', Mask.ATTRIB | Mask.ONLYDIR)

    def test_nonexist_error(self):
        with self.assertRaises(OSError):
            self.inotify.add_watch(self.dir / 'foo', Mask.ATTRIB | Mask.ONLYDIR)

        with self.assertRaises(OSError):
            self.inotify.add_watch(self.dir / 'foo', Mask.ATTRIB)

    def test_move_self(self):
        with open(self.dir / 'foo', 'w'):
            pass

        watch = self.inotify.add_watch(self.dir / 'foo', Mask.MOVE_SELF)

        def test():
            (self.dir / 'foo').rename(self.dir / 'bar')

        events = self.gather_events(test)
        self.assertTrue(any(Mask.MOVE_SELF in event and event.path == self.dir / 'foo' and event.watch is watch for event in events))

    def test_delete_self(self):
        with open(self.dir / 'foo', 'w'):
            pass

        watch = self.inotify.add_watch(self.dir / 'foo', Mask.DELETE_SELF)

        def test():
            (self.dir / 'foo').unlink()

        events = self.gather_events(test)

        self.assertTrue(any(Mask.DELETE_SELF in event and event.path == self.dir / 'foo' and event.watch is watch for event in events))
        self.assertTrue(any(Mask.IGNORED in event and event.path == self.dir / 'foo' and event.watch is watch for event in events))
        self.assertTrue(any(Mask.IGNORED in event and event.path == self.dir for event in events))

    def test_oneshot(self):
        with open(self.dir / 'foo', 'w'):
            pass

        watch = self.inotify.add_watch(self.dir / 'foo', Mask.CREATE | Mask.OPEN | Mask.ONESHOT)

        def test():
            with open(self.dir / 'foo', 'r'):
                pass
            (self.dir / 'foo').unlink()

        events = self.gather_events(test)

        # We check for name is None because only the first event will have a watch value
        self.assertTrue(any(Mask.OPEN in event and event.name is None and event.path == self.dir / 'foo' and event.watch is watch for event in events))
        # The oneshot has already expired, so this should not exist
        self.assertFalse(any(Mask.DELETE in event and event.name is None for event in events))
        # There may or may not be an IGNORED for the watch as well

class TestSyncInotify(unittest.TestCase):

    def watch_events(self) -> Sequence[Event]:
        '''Watch events until an IGNORED is received for the main watch, then
        return the events.'''
        events = []
        with self.inotify as inotify:
            for event in inotify:
                events.append(event)
                if Mask.IGNORED in event and event.watch is self.watch:
                    return events
        raise RuntimeError()

    def gather_events(self, function) -> Sequence[Event]:
        '''Run the function and then watch events until you can return the
        result.'''

        try:
            function()
        finally:
            self.inotify.rm_watch(self.watch)

        return self.watch_events()

    def setUp(self):
        self._dir = TemporaryDirectory()
        self.dir = Path(self._dir.name)
        self.inotify = Inotify()
        self.watch = self.inotify.add_watch(self.dir, Mask.ACCESS | Mask.MODIFY | Mask.ATTRIB | Mask.CLOSE_WRITE | Mask.CLOSE_NOWRITE | Mask.OPEN | Mask.MOVED_FROM | Mask.MOVED_TO | Mask.CREATE | Mask.DELETE | Mask.DELETE_SELF | Mask.MOVE_SELF)

    def tearDown(self):
        self._dir.cleanup()

    def test_diriterated(self):
        def test():
            list(self.dir.iterdir())

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.ISDIR|Mask.OPEN in event and event.path == self.dir for event in events))
        self.assertTrue(any(Mask.ISDIR|Mask.ACCESS in event and event.path == self.dir for event in events))
        self.assertTrue(any(Mask.ISDIR|Mask.CLOSE_NOWRITE in event and event.path == self.dir for event in events))
        self.assertTrue(any(Mask.IGNORED in event and event.path == self.dir for event in events))

    def test_foo_opened_and_closed(self):
        def test():
            with open(self.dir / 'foo', 'w'):
                pass
            with open(self.dir / 'foo', 'r'):
                pass

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.CREATE in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.OPEN in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.CLOSE_WRITE in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.CLOSE_NOWRITE in event and event.path == self.dir / 'foo' for event in events))

    def test_foo_deleted(self):
        def test():
            with open(self.dir / 'foo', 'w'):
                pass

            (self.dir / 'foo').unlink()

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.DELETE in event and event.path == self.dir / 'foo' for event in events))

    def test_foo_write(self):
        def test():
            with open(self.dir / 'foo', 'w') as file:
                file.write('test')

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.CREATE in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.OPEN in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.MODIFY in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.CLOSE_WRITE in event and event.path == self.dir / 'foo' for event in events))

    def test_foo_moved(self):
        def test():
            with open(self.dir / 'foo', 'w'):
                pass

            (self.dir / 'foo').rename(self.dir / 'bar')

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.MOVED_FROM in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.MOVED_TO in event and event.path == self.dir / 'bar' for event in events))
        self.assertEqual(
            next(event.cookie for event in events if Mask.MOVED_FROM in event),
            next(event.cookie for event in events if Mask.MOVED_TO in event),
        )

    def test_foo_attrib(self):
        def test():
            with open(self.dir / 'foo', 'w'):
                pass

            (self.dir / 'foo').chmod(0o777)

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.ATTRIB in event and event.path == self.dir / 'foo' for event in events))

    def test_onlydir_error(self):
        with open(self.dir / 'foo', 'w'):
            pass

        # Will not raise error
        self.inotify.add_watch(self.dir / 'foo', Mask.ATTRIB)

        with self.assertRaises(OSError):
            self.inotify.add_watch(self.dir / 'foo', Mask.ATTRIB | Mask.ONLYDIR)

    def test_nonexist_error(self):
        with self.assertRaises(OSError):
            self.inotify.add_watch(self.dir / 'foo', Mask.ATTRIB | Mask.ONLYDIR)

        with self.assertRaises(OSError):
            self.inotify.add_watch(self.dir / 'foo', Mask.ATTRIB)

    def test_move_self(self):
        with open(self.dir / 'foo', 'w'):
            pass

        watch = self.inotify.add_watch(self.dir / 'foo', Mask.MOVE_SELF)

        def test():
            (self.dir / 'foo').rename(self.dir / 'bar')

        events = self.gather_events(test)
        self.assertTrue(any(Mask.MOVE_SELF in event and event.path == self.dir / 'foo' and event.watch is watch for event in events))

    def test_delete_self(self):
        with open(self.dir / 'foo', 'w'):
            pass

        watch = self.inotify.add_watch(self.dir / 'foo', Mask.DELETE_SELF)

        def test():
            (self.dir / 'foo').unlink()

        events = self.gather_events(test)

        self.assertTrue(any(Mask.DELETE_SELF in event and event.path == self.dir / 'foo' and event.watch is watch for event in events))
        self.assertTrue(any(Mask.IGNORED in event and event.path == self.dir / 'foo' and event.watch is watch for event in events))
        self.assertTrue(any(Mask.IGNORED in event and event.path == self.dir for event in events))

    def test_oneshot(self):
        with open(self.dir / 'foo', 'w'):
            pass

        watch = self.inotify.add_watch(self.dir / 'foo', Mask.CREATE | Mask.OPEN | Mask.ONESHOT)

        def test():
            with open(self.dir / 'foo', 'r'):
                pass
            (self.dir / 'foo').unlink()

        events = self.gather_events(test)

        # We check for name is None because only the first event will have a watch value
        self.assertTrue(any(Mask.OPEN in event and event.name is None and event.path == self.dir / 'foo' and event.watch is watch for event in events))
        # The oneshot has already expired, so this should not exist
        self.assertFalse(any(Mask.DELETE in event and event.name is None for event in events))
        # There may or may not be an IGNORED for the watch as well

    def test_timeout(self):
        with self.inotify as inotify:
            inotify.sync_timeout = 0.1
            list(self.dir.iterdir())
            self.assertTrue(inotify.sync_get())
            for event in inotify:
                pass
            self.assertFalse(inotify.sync_get())

class TestInotifyRepeat(unittest.TestCase):
    async def _actual_test(self):
        events: list[Event] = []

        async def loop(n):
            async for event in n:
                events.append(event)

        with TemporaryDirectory() as dir:
            path = Path(dir) / 'file.txt'
            path.touch()
            with Inotify() as n:
                n.add_watch(path, Mask.ACCESS
                    | Mask.MODIFY
                    | Mask.OPEN
                    | Mask.CREATE
                    | Mask.DELETE
                    | Mask.ATTRIB
                    | Mask.DELETE
                    | Mask.DELETE_SELF
                    | Mask.CLOSE
                    | Mask.MOVE)
                task = create_task(loop(n))
                await asyncio.sleep(0.1)
                with path.open('w'):
                    pass
                await asyncio.sleep(0.1)
                task.cancel()

            with Inotify() as n:
                n.add_watch(path, Mask.ACCESS
                    | Mask.MODIFY
                    | Mask.OPEN
                    | Mask.CREATE
                    | Mask.DELETE
                    | Mask.ATTRIB
                    | Mask.DELETE
                    | Mask.DELETE_SELF
                    | Mask.CLOSE
                    | Mask.MOVE)
                task = create_task(loop(n))
                await asyncio.sleep(0.1)
                path.unlink()
                await asyncio.sleep(0.1)
                task.cancel()

        self.assertTrue(any(Mask.OPEN in event for event in events))
        self.assertTrue(any(Mask.CLOSE_WRITE in event for event in events))
        self.assertTrue(any(Mask.DELETE_SELF in event for event in events))

    def test_events(self):
        run(self._actual_test())

        

if __name__ == '__main__':
    unittest.main()

