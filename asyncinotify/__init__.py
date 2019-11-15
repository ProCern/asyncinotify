import os

# Just to suppress all imports except _meta for setup.py and conf.py
if os.environ.get('ASYNCINOTIFY_DO_NOT_IMPORT') != 'TRUE':
    from .inotify import Inotify, Watch, Event, Mask, InitFlags
    from .error import InotifyError
