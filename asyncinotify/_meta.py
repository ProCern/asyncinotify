# -*- coding: utf-8 -*-
# Copyright © 2019-2021 Taylor C. Richberger
# This code is released under the license described in the LICENSE file

data = dict(
    name='asyncinotify',
    version='3.0.0',
    author='Taylor C. Richberger',
    description='A simple optionally-async python inotify library, focused on simplicity of use and operation, and leveraging modern Python features',
    license='MIT',
    keywords='async inotify',
    url='https://gitlab.com/Taywee/asyncinotify',
    packages=[
        'asyncinotify',
    ],
    package_data={
        "asyncinotify": ["py.typed"],
    },
    zip_safe=False,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Operating System :: POSIX :: Linux',
        'License :: OSI Approved :: MIT License',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Intended Audience :: Developers',
    ],
)
