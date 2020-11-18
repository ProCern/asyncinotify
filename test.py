#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2019 Taylor C. Richberger
# This code is released under the license described in the LICENSE file

import os
import sys

import unittest
from pathlib import Path
sys.path.insert(0, Path(__file__).resolve().parent)
from tempfile import TemporaryDirectory
from asyncinotify import Inotify, Mask, InotifyError
import asyncio

class TestInotify(unittest.TestCase):

    async def watch_events(self):
        '''Watch events until an IGNORED is received for the main watch, then
        return the events.'''
        events = []
        with self.inotify as inotify:
            async for event in inotify:
                events.append(event)
                if Mask.IGNORED in event and event.watch is self.watch:
                    return events

    def gather_events(self, function):
        '''Run the function "soon" in the event loop, and also watch events
        until you can return the result.'''
        loop = asyncio.get_event_loop()
        def wrapper():
            try:
                function()
            finally:
                self.inotify.rm_watch(self.watch)

        loop.call_soon(wrapper)
        return loop.run_until_complete(self.watch_events())

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
            with open(self.dir / 'foo', 'w') as file:
                pass
            with open(self.dir / 'foo', 'r') as file:
                pass

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.CREATE in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.OPEN in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.CLOSE_WRITE in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.CLOSE_NOWRITE in event and event.path == self.dir / 'foo' for event in events))

    def test_foo_deleted(self):
        def test():
            with open(self.dir / 'foo', 'w') as file:
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
            with open(self.dir / 'foo', 'w') as file:
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
            with open(self.dir / 'foo', 'w') as file:
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

        with self.assertRaises(InotifyError):
            self.inotify.add_watch(self.dir / 'foo', Mask.ATTRIB | Mask.ONLYDIR)

    def test_nonexist_error(self):
        with self.assertRaises(InotifyError):
            self.inotify.add_watch(self.dir / 'foo', Mask.ATTRIB | Mask.ONLYDIR)

        with self.assertRaises(InotifyError):
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

    def watch_events(self):
        '''Watch events until an IGNORED is received for the main watch, then
        return the events.'''
        events = []
        with self.inotify as inotify:
            for event in inotify:
                events.append(event)
                if Mask.IGNORED in event and event.watch is self.watch:
                    return events

    def gather_events(self, function):
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
            with open(self.dir / 'foo', 'w') as file:
                pass
            with open(self.dir / 'foo', 'r') as file:
                pass

        events = self.gather_events(test)
        self.assertTrue(all(event.watch is self.watch for event in events))
        self.assertTrue(any(Mask.CREATE in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.OPEN in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.CLOSE_WRITE in event and event.path == self.dir / 'foo' for event in events))
        self.assertTrue(any(Mask.CLOSE_NOWRITE in event and event.path == self.dir / 'foo' for event in events))

    def test_foo_deleted(self):
        def test():
            with open(self.dir / 'foo', 'w') as file:
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
            with open(self.dir / 'foo', 'w') as file:
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
            with open(self.dir / 'foo', 'w') as file:
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

        with self.assertRaises(InotifyError):
            self.inotify.add_watch(self.dir / 'foo', Mask.ATTRIB | Mask.ONLYDIR)

    def test_nonexist_error(self):
        with self.assertRaises(InotifyError):
            self.inotify.add_watch(self.dir / 'foo', Mask.ATTRIB | Mask.ONLYDIR)

        with self.assertRaises(InotifyError):
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

if __name__ == '__main__':
    unittest.main()
