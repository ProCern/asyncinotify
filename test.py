#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2019 Taylor C. Richberger
# This code is released under the license described in the LICENSE file

import sys
import os
import shutil

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from asyncinotify import Event, Inotify, Mask, RecursiveWatcher

if sys.version_info >= (3, 9):
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


class TestRecursiveWatcher(unittest.TestCase):
    def test_get_directories_recursive(self):
        """
        create folder tree as:
        level1.1
            -level2.1
                -level3.1
                    -level4.1
            -level2.2
        level1.2
        """
        with TemporaryDirectory() as tmpdirname:
            tmpdir = Path(tmpdirname)
            (tmpdir / 'level1.1' / 'level2.1' / 'level3.1' / 'level4.1').mkdir(parents=True, exist_ok=True)
            (tmpdir / 'level1.1' / 'level2.2').mkdir(parents=True, exist_ok=True)
            (tmpdir / 'level1.2').mkdir(parents=True, exist_ok=True)
            watcher = RecursiveWatcher(None, None)
            paths = [path for path in watcher._get_directories_recursive(Path(tmpdirname))]
            self.assertEqual(set(paths), {
                tmpdir,
                Path(tmpdirname) / "level1.2",
                Path(tmpdirname) / "level1.1",
                Path(tmpdirname) / "level1.1" / "level2.2",
                Path(tmpdirname) / "level1.1" / "level2.1",
                Path(tmpdirname) / "level1.1" / "level2.1" / "level3.1",
                Path(tmpdirname) / "level1.1" / "level2.1" / "level3.1" / "level4.1",
            })

    def _assert_paths_watched(self, watchers, path_set):
        watched_path_set = {str(watch.path) for watch in watchers.values()}
        self.assertSetEqual(watched_path_set, path_set)

    class _FakeWatcher:
        def __init__(self, path) -> None:
            self.path = path

    def test_assert_paths_watched(self):
        # both empty
        self._assert_paths_watched({}, set())

        # watchers empty
        with self.assertRaises(AssertionError):
            self._assert_paths_watched({}, {"/tmp/path1"})

        # path set empty
        with self.assertRaises(AssertionError):
            self._assert_paths_watched({
                "fd1": self._FakeWatcher(Path("/tmp/path1")),
                "fd2": self._FakeWatcher(Path("/tmp/path2")),
            }, set())

        # identical sets
        self._assert_paths_watched({
            "fd1": self._FakeWatcher(Path("/tmp/path1")),
            "fd2": self._FakeWatcher(Path("/tmp/path2")),
        }, {
            "/tmp/path2",
            "/tmp/path1"
        })

        # diff sets
        with self.assertRaises(AssertionError):
            self._assert_paths_watched({
                "fd1": self._FakeWatcher(Path("/tmp/path1")),
            }, {
                "/tmp/path2",
                "/tmp/path1"
            })

    def _create_file(self, file_path):
        with open(str(file_path), "w") as f:
            f.write(file_path)

    async def _read_events(self, inotify, folder, events):
        watcher = RecursiveWatcher(Path(folder), Mask.CLOSE_WRITE)
        async for event in watcher.watch_recursive(inotify):
            # events/watchers are ephemeral, copy data we want
            events.append((
                event.path,
                event.mask,
            ))

    async def _watch_recursive(self):
        """
        test the cases of folder changes:
        1. create folder
        2. create cascading folders
        3. move folder in from un-monitored folder
        4. move folders out to un-monitored folder
        5. move folder within monitored folders
        6. delete folders
        """
        with TemporaryDirectory() as tmpdirbasename:
            events = []

            tmpdirname = os.path.join(tmpdirbasename, "test")
            os.makedirs(tmpdirname)
            existing_dir = os.path.join(tmpdirname, "existing_dir")
            os.makedirs(existing_dir)
            outside_dir = os.path.join(tmpdirbasename,  "outside")
            os.makedirs(outside_dir)

            with Inotify() as inotify:
                watch_task = create_task(self._read_events(inotify, tmpdirname, events))
                await asyncio.sleep(0.3)

                # existing 2 folders are watched
                self._assert_paths_watched(inotify._watches, {
                    tmpdirname,
                    existing_dir,
                })

                # create file, event
                file_path = os.path.join(tmpdirname, "f1.txt")
                self._create_file(file_path)
                await asyncio.sleep(0.3)

                # still 2 folders watched
                self._assert_paths_watched(inotify._watches, {
                    tmpdirname,
                    existing_dir,
                })

                # create folder and a file inside, no event because of racing
                folder_path = os.path.join(tmpdirname, "d1")
                os.makedirs(folder_path)
                file_path = os.path.join(folder_path, "f2.txt")
                self._create_file(file_path)
                await asyncio.sleep(0.3)

                # one more folder watched
                self._assert_paths_watched(inotify._watches, {
                    tmpdirname,
                    existing_dir,
                    os.path.join(tmpdirname, "d1"),
                })

                # create cascade folders
                folder_path = os.path.join(tmpdirname, "d2", "dd1", "ddd1")
                os.makedirs(folder_path)
                await asyncio.sleep(0.3)

                # 3 more folders watched
                self._assert_paths_watched(inotify._watches, {
                    tmpdirname,
                    existing_dir,
                    os.path.join(tmpdirname, "d1"),
                    os.path.join(tmpdirname, "d2"),
                    os.path.join(tmpdirname, "d2", "dd1"),
                    os.path.join(tmpdirname, "d2", "dd1", "ddd1"),
                })

                # move in folder from outside
                move_folder_path = os.path.join(tmpdirname, "d1", "outside")
                os.rename(outside_dir, move_folder_path)
                await asyncio.sleep(0.3)

                # one more folder watched
                self._assert_paths_watched(inotify._watches, {
                    tmpdirname,
                    existing_dir,
                    os.path.join(tmpdirname, "d1"),
                    os.path.join(tmpdirname, "d2"),
                    os.path.join(tmpdirname, "d2", "dd1"),
                    os.path.join(tmpdirname, "d2", "dd1", "ddd1"),
                    os.path.join(tmpdirname, "d1", "outside"),
                })

                # create file in watched outside folder, event
                file_path = os.path.join(tmpdirname, "d1", "outside", "f3.txt")
                self._create_file(file_path)
                await asyncio.sleep(0.3)

                # move out folder
                folder_path = os.path.join(tmpdirname, "d2", "dd1")
                move_folder_path = os.path.join(tmpdirbasename, "dd1")
                os.rename(folder_path, move_folder_path)
                await asyncio.sleep(0.3)

                # 2 folders not watched
                self._assert_paths_watched(inotify._watches, {
                    tmpdirname,
                    existing_dir,
                    os.path.join(tmpdirname, "d1"),
                    os.path.join(tmpdirname, "d2"),
                    os.path.join(tmpdirname, "d1", "outside"),
                })

                # create file in not watched folder, no event
                file_path = os.path.join(tmpdirbasename, "dd1", "ddd1", "f4.txt")
                self._create_file(file_path)
                await asyncio.sleep(0.3)

                # move folder within
                folder_path = os.path.join(tmpdirname, "existing_dir")
                move_folder_path = os.path.join(tmpdirname, "d1", "existing_dir")
                os.rename(folder_path, move_folder_path)
                await asyncio.sleep(0.3)

                # folders change
                self._assert_paths_watched(inotify._watches, {
                    tmpdirname,
                    os.path.join(tmpdirname, "d1"),
                    os.path.join(tmpdirname, "d2"),
                    os.path.join(tmpdirname, "d1", "outside"),
                    os.path.join(tmpdirname, "d1", "existing_dir")
                })

                # create file in moved folder, event
                file_path = os.path.join(tmpdirname, "d1", "existing_dir", "f5.txt")
                self._create_file(file_path)
                await asyncio.sleep(0.3)

                # delete folder
                folder_path = os.path.join(tmpdirname, "d2")
                os.removedirs(folder_path)
                await asyncio.sleep(0.3)

                # one less folder watched
                self._assert_paths_watched(inotify._watches, {
                    tmpdirname,
                    os.path.join(tmpdirname, "d1"),
                    os.path.join(tmpdirname, "d1", "outside"),
                    os.path.join(tmpdirname, "d1", "existing_dir")
                })

                # delete folders
                shutil.rmtree(os.path.join(tmpdirname, "d1"))
                await asyncio.sleep(0.3)

                # less folders watched
                self._assert_paths_watched(inotify._watches, {
                    tmpdirname,
                })

                watch_task.cancel()
                await asyncio.gather(watch_task, return_exceptions=True)

                # verify events
                self.assertEqual(len(events), 3)
                self.assertEqual(str(events[0][0]), os.path.join(tmpdirname, "f1.txt"))
                self.assertTrue(events[0][1] & Mask.CLOSE_WRITE)

                self.assertEqual(str(events[1][0]), os.path.join(tmpdirname, "d1", "outside", "f3.txt"))
                self.assertTrue(events[1][1] & Mask.CLOSE_WRITE)

                self.assertEqual(str(events[2][0]), os.path.join(tmpdirname, "d1", "existing_dir", "f5.txt"))
                self.assertTrue(events[2][1] & Mask.CLOSE_WRITE)

    def test_watch_recursive(self):
        run(self._watch_recursive())

if __name__ == '__main__':
    unittest.main()
