#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2019 Taylor C. Richberger
# This code is released under the license described in the LICENSE file

import os
os.environ['ASYNCINOTIFY_DO_NOT_IMPORT'] = 'TRUE'

from setuptools import setup
from pathlib import Path

from asyncinotify._meta import data

this_dir = Path(__file__).absolute().parent
readme_path = this_dir / 'README.rst'
#requirements_path = this_dir / 'requirements.txt'

#with requirements_path.open() as file:
#    requirements = [line.strip() for line in file]

with readme_path.open() as file:
    long_description = file.read()

setup(
    long_description=long_description,
    long_description_content_type='text/x-rst',
    #install_requires=requirements,
    **data
)
