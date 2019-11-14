#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2019 Taylor C. Richberger
# This code is released under the license described in the LICENSE file

from pathlib import Path
from asyncinotify import Inotify, Mask
import asyncio

async def main():
    with Inotify() as inotify:
        inotify.add_watch('/tmp', Mask.ACCESS | Mask.MODIFY | Mask.OPEN | Mask.CREATE | Mask.DELETE | Mask.ATTRIB | Mask.CLOSE | Mask.MOVE)
        async for events in inotify:
            print('got batch of events!')
            for event in events:
                print(event)

event_loop = asyncio.get_event_loop()
try:
    event_loop.run_until_complete(main())
except KeyboardInterrupt:
    print('shutting down')

