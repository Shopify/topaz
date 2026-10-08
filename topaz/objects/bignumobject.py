from rpython.rlib.rbigint import rbigint
from rpython.rlib.rfloat import INFINITY
from rpython.rtyper.lltypesystem import lltype, rffi

from topaz.module import ClassDef
from topaz.objects.integerobject import W_IntegerObject
from topaz.objects.numericobject import W_NumericObject


class W_BignumObject(W_IntegerObject):
    # Hidden, like the fixnum class; see W_FixnumObject.
    classdef = ClassDef("Integer", W_IntegerObject.classdef)
    _immutable_fields_ = ["bigint"]

    def __init__(self, space, bigint):
        W_IntegerObject.__init__(self, space)
        self.bigint = bigint

    def __deepcopy__(self, memo):
        obj = super(W_BignumObject, self).__deepcopy__(memo)
        obj.bigint = self.bigint
        return obj

    def get_flag(self, space, name):
        # Integers are always frozen.
        if name == "frozen?":
            return space.w_true
        return W_IntegerObject.get_flag(self, space, name)

    @staticmethod
    def newbigint_fromint(space, intvalue):
        return W_BignumObject(space, rbigint.fromint(intvalue))

    @staticmethod
    def newbigint_fromfloat(space, floatvalue):
        return W_BignumObject(space, rbigint.fromfloat(floatvalue))

    @staticmethod
    def newbigint_fromrbigint(space, bigint):
        return W_BignumObject(space, bigint)

    def int_w(self, space):
        try:
            return self.bigint.toint()
        except OverflowError:
            raise space.error(space.w_RangeError, "bignum too big to convert into `long'")

    def bigint_w(self, space):
        return self.bigint

    def float_w(self, space):
        return self.bigint.tofloat()

    def intmask_w(self, space):
        return rffi.cast(lltype.Signed, self.uintmask_w((space)))

    def uintmask_w(self, space):
        return self.bigint.uintmask()

    def longlongmask_w(self, space):
        return rffi.cast(lltype.SignedLongLong, self.ulonglongmask_w((space)))

    def ulonglongmask_w(self, space):
        return self.bigint.ulonglongmask()

    @classdef.method("inspect")
    def method_inspect(self, space):
        return space.newstr_fromstr(self.bigint.str())

    @classdef.method("to_s", base="int")
    def method_to_s(self, space, base=10):
        if base == 10:
            return space.newstr_fromstr(self.bigint.str())
        from topaz.objects.intobject import format_integer_base
        return space.newstr_fromstr(format_integer_base(space, self.bigint, base))

    @classdef.method("to_f")
    def method_to_f(self, space):
        return space.newfloat(self.bigint.tofloat())

    def new_binop(classdef, name, opname):
        op = getattr(rbigint, opname)
        int_op = getattr(rbigint, 'int_' + opname)

        @classdef.method(name)
        def method(self, space, w_other):
            # Preserve to_int coercion, but keep machine operands unboxed.
            w_other = space.convert_type(w_other, space.w_integer, "to_int")
            if space.is_kind_of(w_other, space.w_fixnum):
                result = int_op(self.bigint, space.int_w(w_other))
            else:
                result = op(self.bigint, space.bigint_w(w_other))
            return space.newbigint_fromrbigint(result)
        method.__name__ = 'method_' + opname
        return method

    method_plus = new_binop(classdef, "+", "add")
    method_sub = new_binop(classdef, "-", "sub")
    method_times = new_binop(classdef, "*", "mul")
    method_and = new_binop(classdef, "&", "and_")
    method_or = new_binop(classdef, "|", "or_")
    method_xor = new_binop(classdef, "^", "xor")

    def floordiv(self, space, other):
        try:
            result = self.bigint.div(other)
        except ZeroDivisionError:
            raise space.error(space.w_ZeroDivisionError, "divided by 0")
        try:
            return space.newint(result.toint())
        except OverflowError:
            return space.newbigint_fromrbigint(result)

    @classdef.method("/")
    def method_divide(self, space, w_other):
        if space.is_kind_of(w_other, space.w_fixnum):
            try:
                result = self.bigint.int_floordiv(space.int_w(w_other))
            except ZeroDivisionError:
                raise space.error(space.w_ZeroDivisionError, "divided by 0")
            return space.newbigint_fromrbigint(result)
        elif space.is_kind_of(w_other, space.w_bignum):
            return self.floordiv(space, space.bigint_w(w_other))
        elif space.is_kind_of(w_other, space.w_float):
            return space.send(space.newfloat(space.float_w(self)), "/", [w_other])
        else:
            return W_NumericObject.retry_binop_coercing(space, self, w_other, "/")

    @classdef.method("fdiv")
    def method_fdiv(self, space, w_other):
        raise space.error(space.w_NotImplementedError, "Integer#fdiv for big integers")

    @classdef.method("<<", other="int")
    def method_left_shift(self, space, other):
        if other >= 0:
            return space.newbigint_fromrbigint(self.bigint.lshift(other))
        else:
            return space.newbigint_fromrbigint(self.bigint.rshift(-other))

    @classdef.method(">>", other="int")
    def method_right_shift(self, space, other):
        if other >= 0:
            return space.newbigint_fromrbigint(self.bigint.rshift(other))
        else:
            return space.newbigint_fromrbigint(self.bigint.lshift(-other))

    @classdef.method("[]", idx="int")
    def method_subscript(self, space, idx):
        if idx < 0:
            return space.newint(0)
        return space.newint(self.bigint.rshift(idx).int_and_(1).toint())

    @classdef.method("~")
    def method_invert(self, space):
        return space.newbigint_fromrbigint(self.bigint.invert())

    @classdef.method("bit_length")
    def method_bit_length(self, space):
        bigint = self.bigint
        if bigint.get_sign() < 0:
            bigint = bigint.invert()
        return space.newint(bigint.bit_length())

    @classdef.method("==")
    def method_eq(self, space, w_other):
        w_other = space.convert_type(w_other, space.w_integer, "to_int")
        if space.is_kind_of(w_other, space.w_fixnum):
            return space.newbool(self.bigint.int_eq(space.int_w(w_other)))
        return space.newbool(self.bigint.eq(space.bigint_w(w_other)))

    @classdef.method("<=>")
    def method_comparator(self, space, w_other):
        w_other = space.convert_type(w_other, space.w_integer, "to_int")
        if space.is_kind_of(w_other, space.w_fixnum):
            other_int = space.int_w(w_other)
            if self.bigint.int_gt(other_int):
                return space.newint(1)
            elif self.bigint.int_eq(other_int):
                return space.newint(0)
            return space.newint(-1)
        other = space.bigint_w(w_other)
        if self.bigint.gt(other):
            return space.newint(1)
        elif self.bigint.eq(other):
            return space.newint(0)
        elif self.bigint.lt(other):
            return space.newint(-1)

    @classdef.method("hash")
    def method_hash(self, space):
        return space.newint(self.bigint.hash())

    @classdef.method("coerce")
    def method_coerce(self, space, w_other):
        if isinstance(w_other, W_BignumObject):
            return space.newarray([w_other, self])
        elif space.getclass(w_other) is space.w_fixnum:
            return space.newarray([
                space.newbigint_fromint(space.int_w(w_other)),
                self,
            ])
        else:
            raise space.error(space.w_TypeError,
                "can't coerce %s to Integer" %
                    space.obj_to_s(space.getclass(w_other))
            )

    @classdef.method("**")
    def method_pow(self, space, w_other):
        if space.getclass(w_other) is space.w_fixnum or space.getclass(w_other) is space.w_bignum:
            exp = space.bigint_w(w_other)
            negative_exponent = False
            if exp.get_sign() < 0:
                negative_exponent = True
                exp = exp.abs()
            result = self.bigint.pow(exp, None)
            if negative_exponent:
                return space.newfloat(1.0 / result.tofloat())
            else:
                return space.newbigint_fromrbigint(result)
        elif space.getclass(w_other) is space.w_float:
            try:
                float_value = space.float_w(self)
            except OverflowError:
                return space.newfloat(INFINITY)
            return space.send(
                space.newfloat(float_value),
                "**",
                [w_other]
            )
        else:
            raise space.error(
                space.w_TypeError,
                "%s can't be coerced into Integer" % (
                    space.obj_to_s(space.getclass(w_other))
                )
            )

    @classdef.method("divmod")
    def method_divmod(self, space, w_other):
        if space.is_kind_of(w_other, space.w_float):
            return space.send(self.method_to_f(space), "divmod", [w_other])
        elif(space.is_kind_of(w_other, space.w_bignum) or
             space.is_kind_of(w_other, space.w_fixnum)):
            try:
                if space.is_kind_of(w_other, space.w_fixnum):
                    div, mod = self.bigint.int_divmod(space.int_w(w_other))
                else:
                    div, mod = self.bigint.divmod(space.bigint_w(w_other))
            except ZeroDivisionError:
                raise space.error(space.w_ZeroDivisionError, "divided by 0")
            return space.newarray([space.newbigint_fromrbigint(div),
                                   space.newbigint_fromrbigint(mod)])
        else:
            raise space.error(
                space.w_TypeError,
                "%s can't be coerced into Integer" % (
                    space.obj_to_s(space.getclass(w_other))
                )
            )

    @classdef.method("gcd")
    def method_gcd(self, space, w_other):
        if space.is_kind_of(w_other, space.w_fixnum):
            other = rbigint.fromint(space.int_w(w_other))
        elif space.is_kind_of(w_other, space.w_bignum):
            other = space.bigint_w(w_other)
        else:
            raise space.error(space.w_TypeError, "not an integer")
        return space.newbigint_fromrbigint(self.bigint.gcd(other))

    @classdef.method("%")
    @classdef.method("modulo")
    def method_mod(self, space, w_other):
        if space.getclass(w_other) is space.w_fixnum:
            try:
                result = self.bigint.int_mod_int_result(space.int_w(w_other))
            except ZeroDivisionError:
                raise space.error(space.w_ZeroDivisionError, "divided by 0")
            return space.newint(result)
        elif space.getclass(w_other) is space.w_float:
            return space.send(self.method_to_f(space), "%", [w_other])
        elif space.getclass(w_other) is space.w_bignum:
            return self.method_mod_bigint_impl(space, space.bigint_w(w_other))
        else:
            raise space.error(
                space.w_TypeError,
                "%s can't be coerced into Integer" % (
                    space.obj_to_s(space.getclass(w_other))
                )
            )

    def method_mod_bigint_impl(self, space, other):
        if not other.tobool():
            raise space.error(space.w_ZeroDivisionError, "divided by 0")
        return space.newbigint_fromrbigint(self.bigint.mod(other))
