from __future__ import absolute_import
import os
import sys

from rpython.rlib.rarithmetic import intmask
from rpython.rlib.rtermios import tcsetattr, tcgetattr, all_constants

from topaz.error import error_for_oserror, ERRNO_LIST
from topaz.module import ModuleDef
from topaz.objects.classobject import W_ClassObject
from topaz.objects.symbolobject import is_label_symbol


class Topaz(object):
    moduledef = ModuleDef("Topaz")

    @moduledef.setup_module
    def setup_module(space, w_mod):
        space.set_const(w_mod, "FIXNUM_MAX", space.newint(sys.maxint))
        w_termioconsts = space.newmodule("TermIOConstants", None)
        space.set_const(w_mod, "TermIOConstants", w_termioconsts)
        for name, value in all_constants.iteritems():
            space.set_const(w_termioconsts, name, space.newint(value))
        space.set_const(w_mod, "ERRNO_LIST", space.newarray([
            space.newarray([space.newsymbol(name), space.newint(code),
                            space.newstr_fromstr(os.strerror(code))])
            for name, code in ERRNO_LIST
        ]))

    @moduledef.function("method_cache_stats")
    def method_method_cache_stats(self, space):
        """[hits, misses, invalidations, {module name => invalidations}]
        of the interpreter's method caches."""
        from topaz.objects.moduleobject import method_cache_state
        w_bumps = space.newhash()
        for name, count in method_cache_state.bumps_by_module.iteritems():
            space.send(w_bumps, "[]=", [space.newstr_fromstr(name), space.newint(count)])
        return space.newarray([
            space.newint(method_cache_state.hits),
            space.newint(method_cache_state.misses),
            space.newint(method_cache_state.state),
            w_bumps,
        ])

    @moduledef.function("label_symbol?", symbol="symbol")
    def method_label_symbolp(self, space, symbol):
        """Whether a Hash inspects the key :symbol as `symbol: `."""
        return space.newbool(is_label_symbol(symbol))

    @moduledef.function("intmask")
    def method_intmask(self, space, w_int):
        if space.is_kind_of(w_int, space.w_fixnum):
            return w_int
        elif space.is_kind_of(w_int, space.w_bignum):
            bigint = space.bigint_w(w_int)
            return space.newint(intmask(bigint.uintmask()))

    @moduledef.function("alias_global", new_name="symbol", old_name="symbol")
    def method_alias_global(self, space, new_name, old_name):
        space.globals.alias(space, new_name, old_name)
        return space.w_nil

    @moduledef.function("convert_type", method="symbol")
    def method_convert_type(self, space, w_obj, w_type, method):
        if not isinstance(w_type, W_ClassObject):
            raise space.error(
                space.w_TypeError, "type argument must be a class")
        return space.convert_type(w_obj, w_type, method)

    @moduledef.function("try_convert_type", method="symbol")
    def method_try_convert_type(self, space, w_obj, w_type, method):
        if not isinstance(w_type, W_ClassObject):
            raise space.error(
                space.w_TypeError, "type argument must be a class")
        return space.convert_type(w_obj, w_type, method, raise_error=False)

    @moduledef.function("compare")
    def method_compare(self, space, w_a, w_b, block=None):
        return space.compare(w_a, w_b, block)

    @moduledef.function("infect", taint="bool", untrust="bool", freeze="bool")
    def method_infect(self, space, w_dest, w_src, taint=True, untrust=True,
                      freeze=False):
        space.infect(
            w_dest, w_src, taint=taint, untrust=untrust, freeze=freeze)
        return self

    @moduledef.function("tcsetattr", fd="int", when="int", mode_w="array")
    def method_tcsetattr(self, space, fd, when, mode_w):
        cc = [space.str_w(w_char) for w_char in space.listview(mode_w[6])]
        mode = (
            space.int_w(mode_w[0]),  # iflag
            space.int_w(mode_w[1]),  # oflag
            space.int_w(mode_w[2]),  # cflag
            space.int_w(mode_w[3]),  # lflag
            space.int_w(mode_w[4]),  # ispeed
            space.int_w(mode_w[5]),  # ospeed
            cc
        )
        try:
            tcsetattr(fd, when, mode)
        except OSError as e:
            raise error_for_oserror(space, e)
        return self

    @moduledef.function("tcgetattr", fd="int")
    def method_tcgetattr(self, space, fd):
        try:
            mode = tcgetattr(fd)
        except OSError as e:
            raise error_for_oserror(space, e)
        mode_w = [
            space.newint(mode[0]),  # iflag
            space.newint(mode[1]),  # oflag
            space.newint(mode[2]),  # cflag
            space.newint(mode[3]),  # lflag
            space.newint(mode[4]),  # ispeed
            space.newint(mode[5]),  # ospeed
            space.newarray([space.newstr_fromstr(cc) for cc in mode[6]])
        ]
        return space.newarray(mode_w)
