from topaz.modules.ffi.type import W_BuiltinType

from rpython.rtyper.lltypesystem import rffi, lltype
from rpython.rlib.objectmodel import compute_unique_id
from rpython.rlib import clibffi, jit

from topaz.modules.ffi import misc

# This will definitely leak memory
registration = {}


class Data(object):
    def __init__(self, space, w_proc, w_callback_info):
        self.space = space
        self.w_proc = w_proc
        self.w_callback_info = w_callback_info

    def invoke(self, ll_args, ll_res):
        space = self.space
        args_w = self._read_args(space, ll_args)
        w_res = space.send(self.w_proc, 'call', args_w)
        self._write_res(space, w_res, ll_res)

    def _read_args(self, space, ll_adrs):
        length = len(self.w_callback_info.arg_types_w)
        args_w = [None] * length
        for i in range(length):
            w_arg_type = self.w_callback_info.arg_types_w[i]
            ll_adr = rffi.cast(rffi.CCHARP, ll_adrs[i])
            assert isinstance(w_arg_type, W_BuiltinType)
            w_arg = w_arg_type.rw_strategy.read(space, ll_adr)
            args_w[i] = w_arg
        return args_w

    def _write_res(self, space, w_obj, ll_adr):
        ll_adr = rffi.cast(rffi.CCHARP, ll_adr)
        w_ret_type = self.w_callback_info.w_ret_type
        assert isinstance(w_ret_type, W_BuiltinType)
        w_ret_type.rw_strategy.write(space, ll_adr, w_obj)


class Closure(object):
    def __init__(self, callback_data):
        # RPython dropped its own closureHeap allocator in favour of libffi's
        # ffi_closure_alloc(), which hands back a writable closure plus the
        # separate executable address that C code must call.
        self.ll_code = lltype.malloc(rffi.VOIDPP.TO, 1, flavor='raw')
        self.heap = clibffi.c_ffi_closure_alloc(
            rffi.cast(rffi.SIZE_T, rffi.sizeof(clibffi.FFI_CLOSUREP.TO)),
            self.ll_code)
        self.callback_data = callback_data
        w_callback_info = self.callback_data.w_callback_info
        space = self.callback_data.space
        if not self.heap:
            raise space.error(space.w_RuntimeError,
                              "libffi failed to allocate a closure")
        self.uid = compute_unique_id(self)
        registration[self.uid] = self
        cls_ptr = rffi.cast(clibffi.FFI_CLOSUREP, self.heap)
        status = clibffi.c_ffi_prep_closure_loc(cls_ptr,
                                                w_callback_info.cif_descr.cif,
                                                invoke,
                                                rffi.cast(rffi.VOIDP, self.uid),
                                                self.ll_code[0])
        if rffi.cast(lltype.Signed, status) != clibffi.FFI_OK:
            space = self.callback_data.space
            raise space.error(space.w_RuntimeError,
                              "libffi failed to build this callback type")

    def write(self, data):
        misc.write_raw_unsigned_data(
            data, rffi.cast(rffi.CCHARP, self.ll_code[0]),
            rffi.sizeof(clibffi.FFI_CLOSUREP))

    def __del__(self):
        if self.heap:
            clibffi.c_ffi_closure_free(self.heap)
            self.heap = lltype.nullptr(rffi.VOIDP.TO)
        if self.ll_code:
            lltype.free(self.ll_code, flavor='raw')
            self.ll_code = lltype.nullptr(rffi.VOIDPP.TO)


@jit.jit_callback("block_callback")
def invoke(ll_cif, ll_res, ll_args, ll_data):
    key = rffi.cast(lltype.Signed, ll_data)
    closure = registration[key]
    closure.callback_data.invoke(ll_args, ll_res)
