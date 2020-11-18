.. asyncinotify documentation master file, created by
   sphinx-quickstart on Fri Nov 15 09:56:23 2019.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. include:: README.rst

Usage
-----

The core of this package is :class:`asyncinotify.inotify.Inotify`.  Most
important Classes may be imported directly from the :mod:`asyncinotify` package.

.. code-block:: python

  from pathlib import Path
  from asyncinotify import Inotify, Mask
  import asyncio

  async def main():
      # Context manager to close the inotify handle after use
      with Inotify() as inotify:
          # Adding the watch can also be done outside of the context manager.
          # __enter__ doesn't actually do anything except return self.
          # This returns an asyncinotify.inotify.Watch instance
          inotify.add_watch('/tmp', Mask.ACCESS | Mask.MODIFY | Mask.OPEN | Mask.CREATE | Mask.DELETE | Mask.ATTRIB | Mask.CLOSE | Mask.MOVE | Mask.ONLYDIR)
          # Iterate events forever, yielding them one at a time
          async for event in inotify:
              # Events have a helpful __repr__.  They also have a reference to
              # their Watch instance.
              print(event)

              # the contained path may or may not be valid UTF-8.  See the note
              # below
              print(repr(event.path))

  loop = asyncio.get_event_loop()
  try:
      loop.run_until_complete(main())
  except KeyboardInterrupt:
      print('shutting down')
  finally:
      loop.run_until_complete(loop.shutdown_asyncgens())
      loop.close()

This will asynchronously watch the /tmp directory and report events it
encounters.

This library also supports synchronous operation, using the
:meth:`asyncinotify.inotify.Inotify.sync_get`` method, or simply using
synchronous iteration.

Motivation
----------

There are a few different python inotify packages.  Most of them either have odd
conventions, expose too much of the underlying C API in a way that I personally
don't like, are badly documented, they work with paths in a non-idiomatic way,
are not asynchronous, or are overengineered compared to the API they are
wrapping.  I find that the last one is true for the majority of them.

I encourage everybody to read the `sources <GitLab_>`_ of this package.  They are
quite simple and easy to understand.

This library

* Works in a very simple way.  It does not have add-ons or extra features beyond
  presenting a very Python interface to the raw inotify functionality.

* Grabs events in bulk and caches them for minor performance gains.

* Leverages IntFlag for all masks and flags, allowing the user to use the
  features of IntFlag, such as seeing individual applied flags in the ``repr``,
  checking for flag set bits with ``in``.

* Exposes all paths via python's pathlib_

* Exposes all the functionality of inotify without depending on the user having
  to interact with any of the underlying mechanics of Inotify.  You should never
  have to touch the inotify or watch descriptors for any reason.

The primary motivation is that this is written to be a Python inotify module
that I would feel comfortable using.

.. warning::

  This package handles the watch paths and event names and paths as
  :class:`pathlib.Path` instances.  These may not be valid utf-8, because Linux
  paths may contain any character except for the null byte, including invalid
  utf-8 sequences.  This library encodes these using python's
  ``surrogateescape``
  handler, to conform to the way the os package does it.  This means that if you
  have invalid utf-8 in a path, you can still handle it correctly and reference
  it as a file, but if you try to print it or convert it (such as using the
  :meth:`str.encode` method), you will get an error unless you explicitly use
  ``surrogateescape``.

  You can read more about the ``surrogateescape`` in the `Python os package
  documentation <ospackage_>`_ and the `codecs error handler <errorhandler_>`_ documentation.

.. toctree::
  :maxdepth: 2
  :caption: Contents:

  doc/asyncinotify

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. _ospackage: https://docs.python.org/3/library/os.html#file-names-command-line-arguments-and-environment-variables
.. _errorhandler: https://docs.python.org/3/library/codecs.html#error-handlers
.. _GitLab: https://gitlab.com/Taywee/asyncinotify
.. _pathlib: https://docs.python.org/3/library/pathlib.html
.. _ReadTheDocs: https://asyncinotify.readthedocs.io/en/latest/
.. _PyPi: https://pypi.org/project/asyncinotify/
