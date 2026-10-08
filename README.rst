Topaz
=====

Topaz is an implementation of the Ruby programming language, written in Python,
using the RPython VM toolchain. Its goals are simplicity of implementation and
performance.

Topaz targets Ruby 4.0 (``RUBY_VERSION`` is ``4.0.0``) and parses Ruby with
`Prism`_, the parser CRuby itself uses, whose C sources are vendored in
``vendor/prism``. It is still far from complete.

Building
--------

You need:

* A checkout of `PyPy`_'s ``main`` branch, which contains RPython. Put the
  checkout's root (not just its ``rpython`` directory) on ``PYTHONPATH``; a
  shallow clone is enough::

      $ git clone --depth 1 https://github.com/pypy/pypy

  Apply the patches in ``tools/rpython-patches`` to it (``git apply``): they
  fix RPython JIT crashes that Topaz runs into.

* A Python 2.7 to run RPython with. PyPy 2.7 is recommended, as translating
  with it is about twice as fast as with CPython 2.7.
* A C compiler, ``make``, and the libffi headers (e.g. ``libffi-dev`` on
  Debian).

To translate run::

    $ pypy /path/to/pypy/rpython/bin/rpython -Ojit targettopaz.py

This compiles Topaz with a JIT into ``bin/topaz``; it takes about five minutes
on a recent machine.

With Nix, for example, ``nix-shell -p pypy27 gcc gnumake pkg-config libffi``
provides everything but the PyPy checkout.

Running the tests
-----------------

The tests run untranslated, on top of Python, using the pytest that comes with
PyPy::

    $ PYTHONPATH=/path/to/pypy pypy /path/to/pypy/pytest.py tests/

To run Topaz directly on top of Python (very slowly) you can do::

    $ PYTHONPATH=/path/to/pypy pypy -m topaz /path/to/file.rb

Prism
-----

``topaz/prism/nodes.py`` is generated from Prism's ``config.yml``. After
upgrading the vendored Prism (see ``vendor/prism/README.md``), regenerate it
with ``python3 topaz/prism/gen.py``, which needs a ``ruby`` to read the YAML.

Profiling with vmprof
--------------------

A translated Topaz can record Ruby call stacks with vmprof. Set
``TOPAZ_VMPROF`` to the output filename::

    $ TOPAZ_VMPROF=/tmp/topaz.prof bin/topaz program.rb

This overwrites the output file and samples CPU time every 10 milliseconds,
including startup, required libraries, and ``at_exit`` handlers. Normal
exit, Ruby ``exit``, and unhandled Ruby exceptions finish the profile before
closing it. Forced termination (for example, SIGKILL or ``exit!``) can leave
an incomplete profile.

Set ``TOPAZ_VMPROF_INTERVAL`` to override the interval in seconds. For
example, to sample every 100 ms::

    $ TOPAZ_VMPROF=/tmp/topaz.prof TOPAZ_VMPROF_INTERVAL=0.1 bin/topaz program.rb

The interval must be at least 0.000001 seconds and less than 1 second.
Longer intervals reduce sampling overhead, especially for deep native stacks.
The setting is only read when ``TOPAZ_VMPROF`` enables profiling.

Install the Python ``vmprof`` package in a separate environment to inspect
the recording::

    $ python3 -m venv /tmp/vmprof-viewer
    $ /tmp/vmprof-viewer/bin/pip install vmprof
    $ /tmp/vmprof-viewer/bin/vmprofshow /tmp/topaz.prof tree

Ruby frames contain the method or block name, source filename, and starting
line. Native frames are enabled automatically on platforms where RPython
supports them (currently x86 Unix); on Linux this needs the system's
``libunwind`` at runtime. After sampling stops, Topaz resolves native
addresses while the process is still alive and saves the symbols in the
profile. On Linux, ELF symbol tables supply local C function names even
without debug information; keep debug information for source lines as well.
Addresses without symbols are shown as
``<native symbol 0x...>``. Symbol resolution adds time at shutdown, outside
the recorded interval. Per-line Ruby sampling is not enabled. RPython
currently labels the interpreter in the file header as ``pypy``; the Ruby
frames themselves use ``rb``. Recording requires a translated executable on
a platform supported by RPython's vmprof; running ``pypy -m topaz`` is not
supported for recording Ruby stacks.

To build without the JIT, replace ``-Ojit`` with ``-O2`` in the build command::

    $ pypy /path/to/pypy/rpython/bin/rpython -O2 targettopaz.py

The translated profiling smoke test checks Ruby caller stacks, Fiber
yield/resume and completion, exception unwinding, and exit handlers. Run it
with the viewer environment::

    $ /tmp/vmprof-viewer/bin/python tools/check_vmprof.py bin/topaz

Add ``--native`` to also require native samples, resolved symbols, and mixed
Ruby/native stacks in the smoke test. For a JIT build, add ``--jit`` to run
longer loops and also require samples from JIT-compiled Ruby code::

    $ /tmp/vmprof-viewer/bin/python tools/check_vmprof.py bin/topaz --native --jit

.. _`PyPy`: https://github.com/pypy/pypy
.. _`Prism`: https://github.com/ruby/prism
