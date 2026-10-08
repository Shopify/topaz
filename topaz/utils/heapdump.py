"""Export RPython's heap graph and the type metadata from this executable."""
import os

from rpython.rlib import jit, rgc, rpath, rzlib
from rpython.rlib.objectmodel import we_are_translated
from rpython.rlib.streamio import open_file_as_stream
from rpython.rtyper.lltypesystem import lltype, rffi

OPEN_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)


class HeapDumpUnsupported(Exception):
    pass


def write_file(path, data):
    stream = open_file_as_stream(path, "wb")
    try:
        stream.write(data)
    finally:
        stream.close()


@jit.dont_look_inside
def dump_heap(path):
    separator = path.rfind(os.sep)
    if os.altsep is not None:
        separator = max(separator, path.rfind(os.altsep))
    start = separator + 1
    assert start >= 0
    directory = path[:start]
    if path[start:] in ("typeids.txt", "typeids.lst"):
        raise ValueError("heap dump filename is reserved for type metadata")
    if not we_are_translated():
        raise HeapDumpUnsupported
    # Read metadata before opening files: untranslated calls fail without
    # creating an empty dump. No Ruby-level Zlib implementation is required.
    compressed = rgc.get_typeids_z()
    data = "".join([compressed[i] for i in range(len(compressed))])
    inflater = rzlib.inflateInit()
    try:
        type_names, finished, unused = rzlib.decompress(
            inflater, data, rzlib.Z_FINISH)
    finally:
        rzlib.inflateEnd(inflater)
    type_ids = rgc.get_typeids_list()
    type_list = "".join(["%d\n" % rffi.cast(lltype.Signed, type_ids[i])
                         for i in range(len(type_ids))])

    # Always refresh metadata: an existing file might belong to another build.
    write_file(rpath.rjoin(directory, "typeids.txt"), type_names)
    write_file(rpath.rjoin(directory, "typeids.lst"), type_list)
    fd = os.open(path, OPEN_FLAGS, 0666)
    try:
        if not rgc.dump_rpy_heap(fd):
            raise HeapDumpUnsupported
    finally:
        os.close(fd)
