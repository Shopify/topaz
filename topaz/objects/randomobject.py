import copy
import os
import time

from rpython.rlib.rarithmetic import intmask, r_uint
from rpython.rlib.rbigint import rbigint
from rpython.rlib.rrandom import Random

from topaz.module import ClassDef
from topaz.objects.objectobject import W_Object
from topaz.objects.rangeobject import W_RangeObject
from topaz.objects.bignumobject import W_BignumObject
from topaz.coerce import Coerce


class W_RandomObject(W_Object):
    classdef = ClassDef("Random", W_Object.classdef)

    def __init__(self, space, seed=0, klass=None):
        W_Object.__init__(self, space, klass)
        self.w_seed = None
        self.random = Random(r_uint(abs(seed)))

    def __deepcopy__(self, memo):
        obj = super(W_RandomObject, self).__deepcopy__(memo)
        obj.w_seed = copy.deepcopy(self.w_seed, memo)
        obj.random = copy.deepcopy(self.random, memo)
        return obj

    @classdef.setup_class
    def setup_class(cls, space, w_cls):
        default = space.send(w_cls, "new")
        space.set_const(w_cls, "DEFAULT", default)

    @classdef.singleton_method("allocate")
    def method_allocate(self, space):
        return W_RandomObject(space, 0, self)

    @classdef.method("initialize")
    def method_initialize(self, space, w_seed=None):
        self.srand(space, w_seed)

    @classdef.method("seed")
    def method_seed(self, space):
        return self.w_seed

    def srand(self, space, seed=None):
        previous_seed = self.w_seed
        if seed is None:
            w_seed = space.newint(intmask(self._generate_seed()))
        else:
            w_seed = space.convert_type(seed, space.w_integer, "to_int")
        self.w_seed = w_seed
        if previous_seed is None:
            value = space.newfloat(self.random.random())
        else:
            value = previous_seed
        self.random = W_RandomObject.seeded_random(space.bigint_w(w_seed))
        return value

    @staticmethod
    def seeded_random(bigint):
        """A Mersenne Twister seeded as CRuby seeds one: the seed's absolute
        value in 32-bit words, least significant first; one word seeds with
        init_genrand, more with init_by_array."""
        bigint = bigint.abs()
        mask = rbigint.fromint(0xffffffff)
        key = []
        while bigint.tobool():
            key.append(r_uint(bigint.and_(mask).touint()))
            bigint = bigint.rshift(32)
        if len(key) <= 1:
            return Random(key[0] if key else r_uint(0))
        random = Random()
        random.init_by_array(key)
        return random

    def limited(self, limit):
        """A uniform integer in [0, limit], drawn as CRuby's limited_rand
        draws it: masked 32-bit words, retrying when above the limit."""
        if limit == 0:
            return r_uint(0)
        mask = limit
        mask |= mask >> 1
        mask |= mask >> 2
        mask |= mask >> 4
        mask |= mask >> 8
        mask |= mask >> 16
        mask |= mask >> 32
        while True:
            val = r_uint(0)
            ok = True
            i = 1
            while i >= 0:
                if (mask >> (i * 32)) & r_uint(0xffffffff):
                    val |= r_uint(self.random.genrand32()) << (i * 32)
                    val &= mask
                    if limit < val:
                        ok = False
                        break
                i -= 1
            if ok:
                return val

    @classdef.method("bytes", n="int")
    def method_bytes(self, space, n):
        if n < 0:
            raise space.error(space.w_ArgumentError, "negative string size (or size too big)")
        # Four bytes from each 32-bit draw, least significant first.
        result = []
        while len(result) < n:
            x = self.random.genrand32()
            for _ in range(4):
                if len(result) < n:
                    result.append(chr(intmask(x & 0xff)))
                x >>= 8
        w_str = space.newstr_fromstr("".join(result))
        space.send(w_str, "force_encoding", [space.newstr_fromstr("BINARY")])
        return w_str

    @classdef.method("rand")
    def method_rand(self, space, w_max=None):
        if w_max is None:
            return space.newfloat(self.random.random())
        elif space.is_kind_of(w_max, space.w_float):
            return self._rand_float(space, w_max)
        elif space.is_kind_of(w_max, space.getclassfor(W_BignumObject)):
            return self._rand_bignum(space, w_max)
        elif space.is_kind_of(w_max, space.getclassfor(W_RangeObject)):
            return self._rand_range(space, w_max)
        else:
            return self._rand_int(space, w_max)

    @classdef.singleton_method("rand")
    def method_singleton_rand(self, space, args_w):
        default = space.find_const(self, "DEFAULT")
        return space.send(default, "rand", args_w)

    def _rand_range(self, space, range):
        first = space.send(range, "first")
        last = space.send(range, "last")
        if (space.is_kind_of(first, space.w_fixnum) and
                space.is_kind_of(last, space.w_fixnum)):
            lo = space.int_w(first)
            span = space.int_w(last) - lo
            if not space.is_true(space.send(range, "exclude_end?")):
                span += 1
            if span <= 0:
                return space.w_nil
            return space.newint(lo + intmask(self.limited(r_uint(span - 1))))
        random = self.random.random()
        if space.is_true(space.send(range, "include?", [last])):
            last = space.send(last, "+", [space.newint(1)])
        if (not space.respond_to(last, "-") or
            not space.respond_to(last, "+")):
                raise space.error(space.w_ArgumentError, "invalid argument")
        diff = space.send(last, "-", [first])
        offset = space.send(diff, "*", [space.newfloat(random)])
        choice = space.send(offset, "+", [first])
        if (not space.is_kind_of(first, space.w_float) and
            not space.is_kind_of(last, space.w_float)):
            choice = space.send(choice, "to_i")
        return choice

    def _rand_float(self, space, float):
        random = self.random.random()
        max = Coerce.float(space, float)
        if max <= 0:
            raise space.error(space.w_ArgumentError, "invalid argument")
        return space.newfloat(random * max)

    def _rand_int(self, space, integer):
        max = Coerce.int(space, integer)
        if max <= 0:
            raise space.error(space.w_ArgumentError, "invalid argument")
        return space.newint(intmask(self.limited(r_uint(max - 1))))

    def _rand_bignum(self, space, bignum):
        random = self.random.random()
        max = Coerce.float(space, bignum)
        if max <= 0:
            raise space.error(space.w_ArgumentError, "invalid argument")
        return space.newbigint_fromfloat(random * max)

    def _generate_seed(self):
        seed = 0
        if os.access('/dev/urandom', os.R_OK):
            file = os.open('/dev/urandom', os.R_OK, 0644)
            bytes = os.read(file, 4)
            os.close(file)
            for b in bytes:
                seed = seed * 0xff + ord(b)
        return seed + int(time.time()) + os.getpid()
