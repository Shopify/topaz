import math
import operator
import sys

from rpython.rlib import jit, rfloat
from rpython.rlib.debug import check_regular_int
from rpython.rlib.objectmodel import specialize
from rpython.rlib.rarithmetic import (r_uint, r_longlong, r_ulonglong,
    ovfcheck, LONG_BIT)
from rpython.rlib.rbigint import rbigint
from rpython.rlib.rfloat import round_away
from rpython.rtyper.lltypesystem import lltype, rffi

from topaz.coerce import Coerce
from topaz.module import ClassDef
from topaz.objects.floatobject import W_FloatObject
from topaz.objects.integerobject import W_IntegerObject
from topaz.objects.numericobject import W_NumericObject
from topaz.objects.objectobject import W_RootObject
from topaz.system import IS_WINDOWS



INTEGER_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def get_step_location(bytecode):
    return "Integer#step %s:%d:in %s" % (
        bytecode.filepath, bytecode.lineno, bytecode.name)


# Integer#step's loop lives here so that the JIT traces it as its own loop
# with the block inlined once, as with the Array iteration builtins; the
# Ruby method in fixnum.rb handles arguments, floats and bignums.
step_driver = jit.JitDriver(
    greens=["bytecode"], reds="auto", name="Integer#step",
    get_printable_location=get_step_location)


def format_integer_base(space, bigint, base):
    """Integer#to_s(base) for 2 <= base <= 36."""
    if not 2 <= base <= 36:
        raise space.error(space.w_ArgumentError, "invalid radix %d" % base)
    assert base >= 0
    return bigint.format(INTEGER_DIGITS[:base])

class FixnumStorage(object):
    def __init__(self, space):
        self.storages = {}

    def get_or_create(self, space, intvalue):
        try:
            storage = self.storages[intvalue]
        except KeyError:
            self.storages[intvalue] = storage = space.send(space.w_object, "new")
        return storage


class W_FixnumObject(W_RootObject):
    _immutable_fields_ = ["intvalue"]

    # Since Ruby 2.4 there is a single Integer class. Fixnums keep a class
    # of their own for their method table, but it is hidden (see
    # ObjectSpace.getnonsingletonclass) and named after Integer.
    classdef = ClassDef("Integer", W_IntegerObject.classdef)

    def __init__(self, space, intvalue):
        check_regular_int(intvalue)
        self.intvalue = intvalue

    def __deepcopy__(self, memo):
        obj = super(W_FixnumObject, self).__deepcopy__(memo)
        obj.intvalue = self.intvalue
        return obj

    def int_w(self, space):
        return self.intvalue

    def bigint_w(self, space):
        return rbigint.fromint(self.intvalue)

    def float_w(self, space):
        return float(self.intvalue)

    def intmask_w(self, space):
        return self.intvalue

    def uintmask_w(self, space):
        return r_uint(self.intvalue)

    def longlongmask_w(self, space):
        return r_longlong(self.intvalue)

    def ulonglongmask_w(self, space):
        return r_ulonglong(self.intvalue)

    def find_instance_var(self, space, name):
        storage = space.fromcache(FixnumStorage).get_or_create(space, self.intvalue)
        return storage.find_instance_var(space, name)

    def set_instance_var(self, space, name, w_value):
        storage = space.fromcache(FixnumStorage).get_or_create(space, self.intvalue)
        storage.set_instance_var(space, name, w_value)

    def instance_variable_names(self, space):
        storage = space.fromcache(FixnumStorage).get_or_create(space, self.intvalue)
        return storage.instance_variable_names(space)

    def set_flag(self, space, name):
        storage = space.fromcache(FixnumStorage).get_or_create(space, self.intvalue)
        storage.set_flag(space, name)

    def unset_flag(self, space, name):
        storage = space.fromcache(FixnumStorage).get_or_create(space, self.intvalue)
        storage.unset_flag(space, name)

    def get_flag(self, space, name):
        # Integers are always frozen.
        if name == "frozen?":
            return space.w_true
        storage = space.fromcache(FixnumStorage).get_or_create(space, self.intvalue)
        return storage.get_flag(space, name)

    @classdef.method("extend")
    @classdef.method("singleton_class")
    def method_singleton_class(self, space):
        raise space.error(space.w_TypeError, "can't define singleton")

    @classdef.method("inspect")
    def method_inspect(self, space):
        return space.newstr_fromstr(str(self.intvalue))

    @classdef.method("to_s", base="int")
    def method_to_s(self, space, base=10):
        if base == 10:
            return space.newstr_fromstr(str(self.intvalue))
        return space.newstr_fromstr(
            format_integer_base(space, rbigint.fromint(self.intvalue), base))

    @classdef.method("to_f")
    def method_to_f(self, space):
        return space.newfloat(float(self.intvalue))

    @classdef.method("to_i")
    @classdef.method("to_int")
    def method_to_i(self, space):
        return self

    def new_binop(classdef, name, func):
        bigint_op = getattr(rbigint, func.__name__ + '_int_int_bigint_result')
        bigint_int_op = getattr(rbigint, 'int_' + func.__name__)
        @classdef.method(name)
        def method(self, space, w_other):
            if space.is_kind_of(w_other, space.w_fixnum):
                other = space.int_w(w_other)
                try:
                    value = ovfcheck(func(self.intvalue, other))
                except OverflowError:
                    return space.newbigint_fromrbigint(
                        bigint_op(self.intvalue, other))
                else:
                    return space.newint(value)
            elif space.is_kind_of(w_other, space.w_bignum):
                result = bigint_int_op(space.bigint_w(w_other), self.intvalue)
                if name == '-':
                    result = result.neg()
                return space.newbigint_fromrbigint(result)
            elif space.is_kind_of(w_other, space.w_float):
                return space.newfloat(func(self.intvalue, space.float_w(w_other)))
            else:
                return W_NumericObject.retry_binop_coercing(space, self, w_other, name)
        method.__name__ = "method_%s" % func.__name__
        return method
    method_add = new_binop(classdef, "+", operator.add)
    method_sub = new_binop(classdef, "-", operator.sub)
    method_mul = new_binop(classdef, "*", operator.mul)

    @classdef.method("floor")
    def method_floor(self, space):
        return self

    def raise_zero_division_error(self, space):
        raise space.error(space.w_ZeroDivisionError, "divided by 0")

    def divide(self, space, w_other):
        if space.is_kind_of(w_other, space.w_fixnum):
            other = space.int_w(w_other)
            try:
                return space.newint(self.intvalue / other)
            except ZeroDivisionError:
                self.raise_zero_division_error(space)
        elif space.is_kind_of(w_other, space.w_bignum):
            return space.send(space.newbigint_fromint(self.intvalue), "/", [w_other])
        elif space.is_kind_of(w_other, space.w_float):
            return space.send(space.newfloat(space.float_w(self)), "/", [w_other])
        else:
            return W_NumericObject.retry_binop_coercing(space, self, w_other, "/")

    @classdef.method("/")
    def method_divide(self, space, w_other):
        return self.divide(space, w_other)

    @classdef.method("div")
    def method_div(self, space, w_other):
        if space.is_kind_of(w_other, space.w_float):
            if space.float_w(w_other) == 0.0:
                self.raise_zero_division_error(space)
            else:
                w_float = space.send(
                    space.newfloat(space.float_w(self)),
                    "/",
                    [w_other]
                )
                w_float = space.newfloat(math.floor(Coerce.float(space, w_float)))
                return space.send(w_float, "to_i")
        else:
            return self.divide(space, w_other)

    @classdef.method("fdiv")
    def method_fdiv(self, space, w_other):
        if space.is_kind_of(w_other, space.w_fixnum):
            other = space.int_w(w_other)
            try:
                res = float(self.intvalue) / float(other)
            except ZeroDivisionError:
                return space.newfloat(math.copysign(rfloat.INFINITY, float(self.intvalue)))
            else:
                return space.newfloat(res)
        elif space.is_kind_of(w_other, space.w_bignum):
            return space.send(space.newbigint_fromint(self.intvalue), "fdiv", [w_other])
        elif space.is_kind_of(w_other, space.w_float):
            other = space.float_w(w_other)
            try:
                res = float(self.intvalue) / other
            except ZeroDivisionError:
                return space.newfloat(math.copysign(rfloat.INFINITY, float(self.intvalue)))
            else:
                return space.newfloat(res)
        else:
            return W_NumericObject.retry_binop_coercing(space, self, w_other, "fdiv")

    @classdef.method("**")
    def method_pow(self, space, w_other):
        if space.is_kind_of(w_other, space.w_fixnum):
            return self.method_pow_int_impl(space, w_other)
        elif space.getclass(w_other) is space.w_float:
            return space.send(
                space.newfloat(float(self.intvalue)), "**", [w_other]
            )
        elif space.getclass(w_other) is space.w_bignum:
            return space.send(
                space.newbigint_fromint(self.intvalue), "**",
                [w_other]
            )
        else:
            raise space.error(space.w_TypeError,
                "%s can't be coerced into Integer" % space.obj_to_s(space.getclass(w_other))
            )

    def method_pow_int_impl(self, space, w_other):
        exp = space.int_w(w_other)
        temp = self.intvalue
        if exp > 0:
            ix = 1
            try:
                while exp > 0:
                    if exp & 1:
                        ix = ovfcheck(ix * temp)
                    exp >>= 1
                    if exp == 0:
                        break
                    temp = ovfcheck(temp * temp)
            except OverflowError:
                return space.send(
                    space.newbigint_fromint(self.intvalue), "**",
                    [w_other]
                )
            return space.newint(ix)
        elif exp == 0:
            return space.newint(1)
        else:
            # A negative power is a Rational: 2 ** -2 is (1/4).
            w_positive = space.send(self, "**", [space.newint(-exp)])
            w_rational = space.send(space.w_kernel, "Rational", [space.newint(1), w_positive])
            return w_rational

    @classdef.method("divmod")
    def method_divmod(self, space, w_other):
        if space.is_kind_of(w_other, space.w_float):
            return space.send(self.method_to_f(space), "divmod", [w_other])
        elif space.is_kind_of(w_other, space.w_bignum):
            return space.send(space.newbigint_fromint(self.intvalue), "divmod", [w_other])
        elif space.is_kind_of(w_other, space.w_fixnum):
            y = space.int_w(w_other)
            if y == 0:
                raise space.error(
                    space.w_ZeroDivisionError,
                    "divided by 0"
                )
            mod = space.int_w(self.method_mod_int_impl(space, y))
            # x - mod is a multiple of y, so this division is exact.
            div = (self.intvalue - mod) // y
            return space.newarray([space.newint(div), space.newint(mod)])
        else:
            raise space.error(
                space.w_TypeError,
                "%s can't be coerced into Integer" % (
                    space.obj_to_s(space.getclass(w_other))
                )
            )

    @classdef.method("__topaz_int_step")
    def method_int_step(self, space, w_limit, w_step, block):
        """Yields self, self + step, ... while within limit. Returns false
        (having done nothing) when limit or step is not a fixnum, so the
        caller falls back to the generic loop."""
        if (not isinstance(w_limit, W_FixnumObject) or
            not isinstance(w_step, W_FixnumObject)):
            return space.w_false
        limit = w_limit.intvalue
        step = w_step.intvalue
        bytecode = block.bytecode
        i = self.intvalue
        # A single loop (one jit_merge_point per function) for both
        # directions.
        while (i <= limit) if step > 0 else (i >= limit):
            step_driver.jit_merge_point(bytecode=bytecode)
            space.invoke_block(block, [space.newint(i)])
            try:
                i = ovfcheck(i + step)
            except OverflowError:
                # The next value would be past any fixnum limit.
                break
        return space.w_true

    @classdef.method("gcd")
    def method_gcd(self, space, w_other):
        if space.is_kind_of(w_other, space.w_fixnum):
            a = self.intvalue
            b = space.int_w(w_other)
            if a != -sys.maxint - 1 and b != -sys.maxint - 1:
                a = abs(a)
                b = abs(b)
                while b != 0:
                    a, b = b, a % b
                return space.newint(a)
        elif not space.is_kind_of(w_other, space.w_bignum):
            raise space.error(space.w_TypeError, "not an integer")
        return space.send(space.newbigint_fromint(self.intvalue), "gcd", [w_other])

    @classdef.method("%")
    @classdef.method("modulo")
    def method_mod(self, space, w_other):
        if space.is_kind_of(w_other, space.w_fixnum):
            return self.method_mod_int_impl(space, space.int_w(w_other))
        elif space.is_kind_of(w_other, space.w_float):
            return space.send(self.method_to_f(space), "%", [w_other])
        elif space.is_kind_of(w_other, space.w_bignum):
            return space.send(space.newbigint_fromint(self.intvalue), "%", [w_other])
        else:
            raise space.error(
                space.w_TypeError,
                "%s can't be coerced into Integer" % (
                    space.obj_to_s(space.getclass(w_other))
                )
            )

    def method_mod_int_impl(self, space, other):
        if other == 0:
            raise space.error(space.w_ZeroDivisionError, "divided by 0")
        return space.newint(self.intvalue % other)

    @classdef.method("<<", other="int")
    def method_left_shift(self, space, other):
        if other < 0:
            return space.newint(self.intvalue >> -other)
        elif other >= LONG_BIT:
            return space.newbigint_fromrbigint(
                rbigint.lshift_int_int_bigint_result(self.intvalue, other))
        else:
            try:
                value = ovfcheck(self.intvalue << other)
            except OverflowError:
                return space.newbigint_fromrbigint(
                    rbigint.lshift_int_int_bigint_result(self.intvalue, other))
            else:
                return space.newint(value)

    @classdef.method(">>", other="int")
    def method_right_shift(self, space, other):
        if other < 0:
            return space.newint(self.intvalue << -other)
        else:
            return space.newint(self.intvalue >> other)

    def new_bitwise_op(classdef, name, func):
        bigint_int_op = getattr(rbigint, 'int_' + func.__name__)
        @classdef.method(name)
        def method(self, space, w_other):
            w_other = space.convert_type(w_other, space.w_integer, "to_int")
            if space.is_kind_of(w_other, space.w_fixnum):
                other = space.int_w(w_other)
                return space.newint(func(self.intvalue, other))
            elif space.is_kind_of(w_other, space.w_bignum):
                return space.newbigint_fromrbigint(
                    bigint_int_op(space.bigint_w(w_other), self.intvalue))
            else:
                return W_NumericObject.retry_binop_coercing(space, self, w_other, name)
        method.__name__ = "method_%s" % func.__name__
        return method
    method_and = new_bitwise_op(classdef, "&", operator.and_)
    method_or = new_bitwise_op(classdef, "|", operator.or_)
    method_xor = new_bitwise_op(classdef, "^", operator.xor)

    @classdef.method("~")
    def method_invert(self, space):
        return space.newint(~self.intvalue)

    @classdef.method("==")
    @classdef.method("equal?")
    def method_eq(self, space, w_other):
        if isinstance(w_other, W_FixnumObject):
            return space.newbool(self.comparator(space, space.int_w(w_other)) == 0)
        elif isinstance(w_other, W_FloatObject):
            return space.newbool(self.comparator(space, space.float_w(w_other)) == 0)
        else:
            return space.send(w_other, "==", [self])

    @classdef.method("!=")
    def method_ne(self, space, w_other):
        return space.newbool(space.send(self, "==", [w_other]) is space.w_false)

    def new_bool_op(classdef, name, func):
        @classdef.method(name)
        def method(self, space, w_other):
            if space.is_kind_of(w_other, space.w_float):
                return space.newbool(func(self.intvalue, space.float_w(w_other)))
            elif space.is_kind_of(w_other, space.w_fixnum):
                return space.newbool(func(self.intvalue, space.int_w(w_other)))
            else:
                return W_NumericObject.retry_binop_coercing(space, self, w_other, name, raise_error=True)
        method.__name__ = "method_%s" % func.__name__
        return method
    method_lt = new_bool_op(classdef, "<", operator.lt)
    method_lte = new_bool_op(classdef, "<=", operator.le)
    method_gt = new_bool_op(classdef, ">", operator.gt)
    method_gte = new_bool_op(classdef, ">=", operator.ge)

    @classdef.method("<=>")
    def method_comparator(self, space, w_other):
        if isinstance(w_other, W_FixnumObject):
            return space.newint(self.comparator(space, space.int_w(w_other)))
        elif isinstance(w_other, W_FloatObject):
            return space.newint(self.comparator(space, space.float_w(w_other)))
        else:
            return space.w_nil

    @specialize.argtype(2)
    def comparator(self, space, other):
        if self.intvalue < other:
            return -1
        elif self.intvalue == other:
            return 0
        elif self.intvalue > other:
            return 1
        return 1

    @classdef.method("hash")
    def method_hash(self, space):
        return self

    if IS_WINDOWS:
        @classdef.method("size")
        def method_size(self, space):
            # RPython translation is always 32bit on Windows
            return space.newint(4)
    else:
        @classdef.method("size")
        def method_size(self, space):
            return space.newint(rffi.sizeof(lltype.typeOf(self.intvalue)))

    @classdef.method("coerce")
    def method_coerce(self, space, w_other):
        if space.is_kind_of(w_other, space.w_integer):
            return space.newarray([w_other, self])
        # Anything else, as floats.
        return space.newarray([space.send(self, "Float", [w_other]),
                               space.newfloat(float(self.intvalue))])

    @classdef.method("chr")
    def method_chr(self, space):
        if self.intvalue > 255 or self.intvalue < 0:
            raise space.error(space.w_RangeError, "%d out of char range" % self.intvalue)
        else:
            return space.newstr_fromstr(chr(self.intvalue))

    @classdef.method("[]", idx="int")
    def method_subscript(self, space, idx):
        if idx < 0:
            return space.newint(0)
        if idx >= LONG_BIT:
            return space.newint(1 if self.intvalue < 0 else 0)
        return space.newint(int(bool(self.intvalue & (1 << idx))))

    @classdef.method("bit_length")
    def method_bit_length(self, space):
        value = self.intvalue
        if value < 0:
            value = ~value
        n = 0
        while value:
            value >>= 1
            n += 1
        return space.newint(n)


class W_MutableFixnumObject(W_FixnumObject):
    _immutable_fields_ = []

    def set_intvalue(self, intvalue):
        check_regular_int(intvalue)
        self.intvalue = intvalue
