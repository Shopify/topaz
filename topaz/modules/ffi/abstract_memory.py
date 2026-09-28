from topaz.objects.objectobject import W_Object
from topaz.module import ClassDef
from rpython.rtyper.lltypesystem import rffi, lltype

from topaz.modules.ffi import type as ffitype


def new_put_method(typeindex):
    rw_strategy = ffitype.rw_strategies[typeindex]
    sizeof_type = ffitype.lltype_sizes[typeindex]

    def put_method(self, space, offset, w_value):
        offset_ptr = rffi.ptradd(rffi.cast(rffi.CCHARP, self.ptr), offset)
        raise_if_out_of_bounds(space, offset, self.sizeof_memory, sizeof_type)
        rw_strategy.write(space, offset_ptr, w_value)
    return put_method


def new_get_method(typeindex):
    rw_strategy = ffitype.rw_strategies[typeindex]
    sizeof_type = ffitype.lltype_sizes[typeindex]

    def get_method(self, space, offset):
        offset_ptr = rffi.ptradd(rffi.cast(rffi.CCHARP, self.ptr), offset)
        raise_if_out_of_bounds(space, offset, self.sizeof_memory, sizeof_type)
        return rw_strategy.read(space, offset_ptr)
    return get_method


def new_write_method(type_str):
    put_method_name = 'put_' + type_str

    def write_method(self, space, w_value):
        space.send(self, put_method_name, [space.newint(0), w_value])
    return write_method


def new_read_method(type_str):
    get_method_name = 'get_' + type_str

    def read_method(self, space):
        return space.send(self, get_method_name, [space.newint(0)])
    return read_method


def raise_if_out_of_bounds(space, offset, size, sizeof_type):
    if offset < 0 or offset >= size:
        raise memory_index_error(space, offset, sizeof_type)


def memory_index_error(space, offset, size):
    return space.error(space.w_IndexError,
                       "Memory access offset=%s size=%s is out of bounds"
                       % (offset, size))


class W_AbstractMemoryObject(W_Object):
    classdef = ClassDef('FFI::AbstractMemory', W_Object.classdef)
    ptr = lltype.nullptr(rffi.VOIDP.TO)
    _immutable_fields_ = ['ptr']

    @classdef.singleton_method('allocate')
    def singleton_method_allocate(self, space):
        return W_AbstractMemoryObject(space)

    def check_range(self, space, offset, nbytes):
        if offset < 0 or nbytes < 0 or offset + nbytes > self.sizeof_memory:
            raise memory_index_error(space, offset, nbytes)

    # Bytes and C strings, for any pointer (memory from C has an unknown
    # size, so only MemoryPointer is bounds checked).

    @classdef.method("put_bytes", offset='int', string='str', str_offset='int',
                     nbytes='int')
    def method_put_bytes(self, space, offset, string, str_offset=0, nbytes=-1):
        if str_offset < 0 or str_offset > len(string):
            raise space.error(space.w_IndexError, "invalid string offset")
        if nbytes < 0:
            nbytes = len(string) - str_offset
        if str_offset + nbytes > len(string):
            raise space.error(space.w_IndexError, "invalid length")
        self.check_range(space, offset, nbytes)
        with rffi.scoped_view_charp(string) as cstring:
            rffi.c_memcpy(
                rffi.ptradd(rffi.cast(rffi.CCHARP, self.ptr), offset),
                rffi.cast(rffi.CONST_VOIDP, rffi.ptradd(cstring, str_offset)),
                nbytes
            )
        return self

    @classdef.method("get_bytes", offset='int', nbytes='int')
    def method_get_bytes(self, space, offset, nbytes):
        self.check_range(space, offset, nbytes)
        return space.newstr_fromstr(rffi.charpsize2str(
            rffi.ptradd(rffi.cast(rffi.CCHARP, self.ptr), offset), nbytes))

    @classdef.method("get_string", offset='int', length='int')
    def method_get_string(self, space, offset, length=-1):
        """The NUL-terminated string at offset, reading at most length
        bytes."""
        start = rffi.ptradd(rffi.cast(rffi.CCHARP, self.ptr), offset)
        limit = self.sizeof_memory - offset
        if length >= 0 and length < limit:
            limit = length
        n = 0
        while n < limit and start[n] != '\x00':
            n += 1
        return space.newstr_fromstr(rffi.charpsize2str(start, n))

    @classdef.method("put_string", offset='int', string='str')
    def method_put_string(self, space, offset, string):
        self.check_range(space, offset, len(string) + 1)
        start = rffi.ptradd(rffi.cast(rffi.CCHARP, self.ptr), offset)
        for i in range(len(string)):
            start[i] = string[i]
        start[len(string)] = '\x00'
        return self

    @classdef.setup_class
    def setup_class(cls, space, w_cls):
        long_in_bits = 8 * rffi.sizeof(rffi.LONG)
        for orig, alias in [
                ('int8', 'char'),
                ('uint8', 'uchar'),
                ('int16', 'short'),
                ('uint16', 'ushort'),
                ('int32', 'int'),
                ('uint32', 'uint'),
                ('int64', 'long_long'),
                ('uint64', 'ulong_long'),
                ('float32', 'float'),
                ('float64', 'double'),
                ('int' + str(long_in_bits), 'long'),
                ('uint' + str(long_in_bits), 'ulong')]:
            for prefix in ['put_', 'get_', 'write_', 'read_']:
                space.send(w_cls, 'alias_method',
                           [space.newsymbol(prefix + alias),
                            space.newsymbol(prefix + orig)])


W_AMO = W_AbstractMemoryObject
for t in [ffitype.INT8, ffitype.INT16, ffitype.INT32, ffitype.INT64,
          ffitype.UINT8, ffitype.UINT16, ffitype.UINT32, ffitype.UINT64,
          ffitype.FLOAT32, ffitype.FLOAT64,
          ffitype.POINTER]:
    tn = ffitype.type_names[t].lower()
    setattr(W_AMO, 'method_put_' + tn,
            W_AMO.classdef.method('put_' + tn, offset='int')(
                new_put_method(t)))
    setattr(W_AMO, 'method_get_' + tn,
            W_AMO.classdef.method('get_' + tn, offset='int')(
                new_get_method(t)))
    setattr(W_AMO, 'method_write_' + tn,
            W_AMO.classdef.method('write_' + tn)(
                new_write_method(tn)))
    setattr(W_AMO, 'method_read_' + tn,
            W_AMO.classdef.method('read_' + tn)(
                new_read_method(tn)))
