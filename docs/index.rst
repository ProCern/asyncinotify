.. asyncinotify documentation master file, created by
   sphinx-quickstart on Fri Nov 15 09:56:23 2019.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. include:: ../README.rst

.. warning::

  This package handles the watch paths and event names and paths as
  :class:`pathlib.Path` instances.  These might not be valid utf-8, because Linux
  paths may contain any character except for the null byte, including invalid
  utf-8 sequences.  This library uses ``os.fsencode`` and ``os.fsdecode`` on
  paths to obtain paths the same way that Python natively does.

  You can read more about Python's path handling in the
  `filesystem encoding and error handler <https://docs.python.org/3/glossary.html#term-filesystem-encoding-and-error-handler>`_
  section of the glossary. This section links to the relevant places, and you
  can use some of this to figure out how to handle non-UTF-8 sequences on a
  UTF-8 system.


.. toctree::
  :maxdepth: 2
  :caption: Contents:

  asyncinotify

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. _ospackage: https://docs.python.org/3/library/os.html#file-names-command-line-arguments-and-environment-variables
.. _errorhandler: https://docs.python.org/3/library/codecs.html#error-handlers
.. _GitHub: https://github.com/absperf/asyncinotify
.. _pathlib: https://docs.python.org/3/library/pathlib.html
.. _ReadTheDocs: https://asyncinotify.readthedocs.io/en/latest/
.. _PyPi: https://pypi.org/project/asyncinotify/
