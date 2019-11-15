#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2019 Taylor C. Richberger
# This code is released under the license described in the LICENSE file

class InotifyError(RuntimeError):
    '''Simple inotify error type, thrown for all errors in inotify ffi calls'''
