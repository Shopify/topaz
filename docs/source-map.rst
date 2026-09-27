Source Code Map
===============

This document is a map of the source code, it describes what many of the
directories/files contain.

``ast.py``
----------

This contains each of the AST node classes. Each of these is responsible for
encoding the structure of the program, and compiling itself to bytecode.

``astcompiler.py``
------------------

This contains utility classes for compiling ASTs to bytecode.

``coerce.py``
-------------

This contains logic for performing type coercion on Ruby objects. It contains
implementations for behaviors like, "this Ruby function takes an Integer
argument".

``executioncontext.py``
------------------------

This contains logic specific to the current thread of execution in Ruby. It
maintains things like the Ruby call stack.

``frame.py``
-------------

This contains Ruby frame objects, and associated logic for manipulating them.

``gateway.py``
---------------

This contains logic for exposing RPython functions in Ruby.

``interpreter.py``
-------------------

This contains the bytecode interpreter itself.

``main.py``
------------

This contains the command line entry-point, including things like argument
parsing logic.

``module.py``
--------------

This contains an API for exposing RPython classes in Ruby, it should be merged
with ``gateway.py``.

``objspace.py``
----------------

This contains the ``ObjectSpace`` (unrelated to Ruby's ``ObjectSpace`` module),
it is responsible for encoding the behaviors of Ruby, for example it contains
methods like ``find_const``, ``send``, and methods for creating new Ruby
objects from RPython ones.

``prism/``
-----------

Parsing. Ruby source is parsed by `Prism <https://github.com/ruby/prism>`_,
the parser CRuby uses, whose C sources are vendored in ``vendor/prism``.
``prism/binding.py`` calls it, ``prism/nodes.py`` (generated from Prism's
``config.yml`` by ``prism/gen.py``) loads the syntax tree it serializes, and
``prism/translate.py`` turns that into Topaz's AST.

``modules/``
------------

This contains built-in Ruby ``Module`` objects. There is one ``Module`` per file.

``objects/``
------------

This contains built-in Ruby ``Class`` objects. There is one ``Class`` per file.
