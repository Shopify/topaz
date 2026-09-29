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

.. _`PyPy`: https://github.com/pypy/pypy
.. _`Prism`: https://github.com/ruby/prism
