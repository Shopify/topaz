"""Low-level binding to Prism's C library.

Prism is compiled into the Topaz binary from the vendored sources in
vendor/prism.  The only entry point used is pm_serialize_parse(), which
parses a source string and serializes the resulting syntax tree into a
buffer; topaz.prism.nodes loads that serialization back into RPython
objects.
"""

import os

import py

from rpython.rtyper.lltypesystem import lltype, rffi
from rpython.tool.udir import udir
from rpython.translator.tool.cbuild import ExternalCompilationInfo


PRISM_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir,
    "vendor", "prism"
)
PRISM_DIR = os.path.normpath(PRISM_DIR)

_SOURCES = [
    "diagnostic.c", "encoding.c", "node.c", "options.c", "pack.c",
    "prettyprint.c", "prism.c", "regexp.c", "serialize.c",
    "static_literals.c", "token_type.c",
    "util/pm_buffer.c", "util/pm_char.c", "util/pm_constant_pool.c",
    "util/pm_integer.c", "util/pm_list.c", "util/pm_memchr.c",
    "util/pm_newline_list.c", "util/pm_string.c", "util/pm_strncasecmp.c",
    "util/pm_strpbrk.c",
]


def _copy_sources():
    # RPython only compiles separate .c files that live under its own tree
    # or under the session's udir, so compile copies of Prism's.
    target = udir.join("prism")
    paths = []
    for name in _SOURCES:
        dest = target.join(name)
        dest.dirpath().ensure(dir=True)
        py.path.local(os.path.join(PRISM_DIR, "src", name)).copy(dest)
        paths.append(dest)
    return paths


eci = ExternalCompilationInfo(
    includes=["prism.h"],
    include_dirs=[os.path.join(PRISM_DIR, "include")],
    separate_module_files=_copy_sources(),
    # Leave out the parts of Prism that Topaz has no use for.
    compile_extra=[
        "-DPRISM_EXPORT_SYMBOLS",
        "-DPRISM_EXCLUDE_JSON", "-DPRISM_EXCLUDE_PACK",
        "-DPRISM_EXCLUDE_PRETTYPRINT",
    ],
)

# pm_buffer_t is treated as an opaque blob of pm_buffer_sizeof() bytes.
pm_buffer_sizeof = rffi.llexternal(
    "pm_buffer_sizeof", [], rffi.SIZE_T, compilation_info=eci,
    releasegil=False,
)
pm_buffer_init = rffi.llexternal(
    "pm_buffer_init", [rffi.VOIDP], rffi.UCHAR, compilation_info=eci,
    releasegil=False,
)
pm_buffer_value = rffi.llexternal(
    "pm_buffer_value", [rffi.VOIDP], rffi.CCHARP, compilation_info=eci,
    releasegil=False,
)
pm_buffer_length = rffi.llexternal(
    "pm_buffer_length", [rffi.VOIDP], rffi.SIZE_T, compilation_info=eci,
    releasegil=False,
)
pm_buffer_free = rffi.llexternal(
    "pm_buffer_free", [rffi.VOIDP], lltype.Void, compilation_info=eci,
    releasegil=False,
)
pm_serialize_parse = rffi.llexternal(
    "pm_serialize_parse",
    [rffi.VOIDP, rffi.CCHARP, rffi.SIZE_T, rffi.CCHARP], lltype.Void,
    compilation_info=eci,
)


# Values for the "version" option; see pm_options_version_t in options.h.
VERSION_CRUBY_4_0 = 3

# Command line flags; see serialization.md.
COMMAND_LINE_E = 0x2


class Scope(object):
    """Local variables of an enclosing scope, e.g. of a Binding being
    eval'd in."""

    def __init__(self, locals):
        self.locals = locals


def _u32(value, out):
    for i in range(4):
        out.append(chr((value >> (8 * i)) & 0xff))


def _bytes(s, out):
    _u32(len(s), out)
    for c in s:
        out.append(c)


def serialize_options(filepath, lineno, scopes, command_line=0):
    """Encode parser options in the format pm_options_read() expects."""
    out = []
    _bytes(filepath, out)
    _u32(lineno, out)
    _bytes("", out)                    # encoding: the default, UTF-8
    out.append(chr(0))                 # frozen_string_literal: unset
    out.append(chr(command_line))
    out.append(chr(VERSION_CRUBY_4_0))
    out.append(chr(0))                 # encoding_locked
    out.append(chr(0))                 # main_script
    out.append(chr(0))                 # partial_script
    out.append(chr(0))                 # freeze
    _u32(len(scopes), out)
    for scope in scopes:
        _u32(len(scope.locals), out)
        out.append(chr(0))             # forwarding
        for name in scope.locals:
            _bytes(name, out)
    return "".join(out)


def serialize_parse(source, options):
    """Parse `source` and return Prism's serialization of its syntax tree
    (including any syntax errors)."""
    size = rffi.cast(lltype.Signed, pm_buffer_sizeof())
    raw = lltype.malloc(rffi.CCHARP.TO, size, flavor="raw")
    try:
        buf = rffi.cast(rffi.VOIDP, raw)
        if not rffi.cast(lltype.Signed, pm_buffer_init(buf)):
            raise MemoryError
        try:
            with rffi.scoped_nonmovingbuffer(source) as c_source:
                with rffi.scoped_nonmovingbuffer(options) as c_options:
                    pm_serialize_parse(
                        buf, c_source, rffi.cast(rffi.SIZE_T, len(source)),
                        c_options
                    )
            length = rffi.cast(lltype.Signed, pm_buffer_length(buf))
            return rffi.charpsize2str(pm_buffer_value(buf), length)
        finally:
            pm_buffer_free(buf)
    finally:
        lltype.free(raw, flavor="raw")
