"""Resolve native samples while their executable and libraries are still loaded."""
import os

from rpython.rlib import rvmprof
from rpython.rlib.rstruct.runpack import runpack
from rpython.rlib.rvmprof import cintf
from rpython.rlib.streamio import fdopen_as_stream
from rpython.rtyper.lltypesystem import lltype, rffi
from rpython.translator.tool.cbuild import ExternalCompilationInfo


NATIVE_SUPPORTED = cintf.NATIVE_PROFILING_SUPPORTED
WORD_SIZE = rffi.sizeof(rffi.LONG)
_resolve_addr = rffi.llexternal(
    "topaz_vmprof_resolve_addr",
    [rffi.VOIDP, rffi.CCHARP, rffi.INT, rffi.INTP, rffi.CCHARP, rffi.INT],
    lltype.Void,
    compilation_info=ExternalCompilationInfo(
        includes=["symboltable.h"],
        include_dirs=[str(cintf.SHARED), str(cintf.BACKTRACE)],
        separate_module_files=[os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "vmprof_native.c")],
        post_include_bits=[
            "void topaz_vmprof_resolve_addr(void *, char *, int, int *, char *, int);"],
    ),
)


def read_exact(stream, size):
    result = stream.read(size)
    assert result is not None
    if len(result) != size:
        raise rvmprof.VMProfError("truncated profile during native symbol resolution")
    return result


def read_word(stream):
    return runpack("l", read_exact(stream, WORD_SIZE))


def pack_word(value):
    with lltype.scoped_alloc(rffi.LONGP.TO, 1) as buffer:
        buffer[0] = rffi.cast(rffi.LONG, value)
        return rffi.charpsize2str(rffi.cast(rffi.CCHARP, buffer), WORD_SIZE)


def skip_string(stream):
    size = read_word(stream)
    if size < 0:
        raise rvmprof.VMProfError("invalid profile string length")
    stream.seek(size, 1)


def native_addresses(stream):
    # Only read the format emitted by RPython, with this process's word size.
    # Version 7 additionally stores an eight-byte timestamp per sample.
    read_exact(stream, 5 * WORD_SIZE)
    version = 0
    memory = False
    addresses = {}
    while True:
        position = stream.tell()
        marker = read_exact(stream, 1)
        if marker == "\x05":
            version = runpack(">h", read_exact(stream, 2))
            if version != 6 and version != 7:
                raise rvmprof.VMProfError("unsupported profile version for native symbols")
            flags = ord(read_exact(stream, 1)[0])
            if not flags & 8:
                raise rvmprof.VMProfError("expected an RPython profile")
            memory = bool(flags & 1)
            read_exact(stream, ord(read_exact(stream, 1)[0]))
        elif marker == "\x01":
            read_word(stream)  # sample count
            depth = read_word(stream)
            if depth < 0 or depth > 65536 or depth & 1:
                raise rvmprof.VMProfError("invalid native profile stack depth")
            for i in range(depth // 2):
                kind = read_word(stream)
                address = read_word(stream)
                if kind == 7:  # VMPROF_NATIVE_TAG
                    addresses[address] = None
            read_word(stream)  # thread id
            if memory:
                read_word(stream)
            if version == 7:
                read_exact(stream, 8)
        elif marker == "\x02" or marker == "\x08":
            read_word(stream)  # code id
            skip_string(stream)
        elif marker == "\x06":
            read_exact(stream, 24)  # timeval and timezone
        elif marker == "\x07":
            skip_string(stream)
            skip_string(stream)
        elif marker == "\x03":
            trailer = marker + read_exact(stream, 24)
            return addresses, position, trailer
        else:
            raise rvmprof.VMProfError("unexpected profile record during native symbol resolution")


def resolve_name(address):
    with lltype.scoped_alloc(rffi.CCHARP.TO, 1024, zero=True) as name:
        with lltype.scoped_alloc(rffi.CCHARP.TO, 1024, zero=True) as filename:
            with lltype.scoped_alloc(rffi.INTP.TO, 1, zero=True) as lineno:
                # vmprof sets the low bit to distinguish native addresses.
                _resolve_addr(rffi.cast(rffi.VOIDP, address & ~1),
                              name, 1024, lineno, filename, 1024)
                name[1023] = "\x00"
                filename[1023] = "\x00"
                symbol = rffi.charp2str(name)[:480].replace(":", ";")
                path = rffi.charp2str(filename)[:480].replace(":", ";")
                line = rffi.cast(lltype.Signed, lineno[0])
    if not symbol:
        symbol = "<native symbol 0x%x>" % address
    if not path:
        path = "-"
    return "n:%s:%d:%s" % (symbol, line, path)


def write_native_symbols(fd):
    # disable() has flushed samples and written the trailer but leaves fd
    # open. Insert symbol records before that trailer, where every reader
    # will see them, and retain the original recording end time.
    stream = fdopen_as_stream(os.dup(fd), "r+b")
    try:
        stream.seek(0, 0)
        addresses, position, trailer = native_addresses(stream)
        stream.seek(position, 0)
        try:
            for address in addresses:
                name = resolve_name(address)
                stream.write("\x08" + pack_word(address) +
                             pack_word(len(name)) + name)
        finally:
            stream.write(trailer)
    finally:
        stream.close()
