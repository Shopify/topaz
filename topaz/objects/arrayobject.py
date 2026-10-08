import copy

from rpython.rlib import jit
from rpython.rlib.objectmodel import specialize
from rpython.rlib.listsort import make_timsort_class
from rpython.rlib.rarithmetic import intmask, r_uint
from rpython.rlib.rbigint import rbigint

from topaz.coerce import Coerce
from topaz.module import ClassDef, check_frozen
from topaz.modules.enumerable import Enumerable
from topaz.objects.objectobject import W_Object
from topaz.objects.intobject import W_FixnumObject
from topaz.objects.bignumobject import W_BignumObject
from topaz.utils.packing.pack import RPacker


BaseRubySorter = make_timsort_class()
BaseRubySortBy = make_timsort_class()


def get_each_location(bytecode):
    return "Array#each %s:%d:in %s" % (
        bytecode.filepath, bytecode.lineno, bytecode.name)


# Its own loop for the JIT: with each written in Ruby, every trace through
# an iterating method inlined the whole iteration (a while loop, a yield and
# a block frame per element), which made the traces of Rails code too long
# to compile. A loop here is traced from here, with the block inlined once.
each_driver = jit.JitDriver(
    greens=["bytecode"], reds="auto", name="Array#each",
    get_printable_location=get_each_location,
)


# Enumerable's versions of these go through each_entry, which wraps every
# element in a `|*e|` splat array and a second block frame. Rails calls
# each_with_index / include? / any? on arrays tens of thousands of times per
# request, so Array gets direct loops with their own JIT drivers.
def _enum_driver(name):
    return jit.JitDriver(
        greens=["bytecode"], reds="auto", name="Array#" + name,
        get_printable_location=get_each_location,
    )


each_with_index_driver = _enum_driver("each_with_index")
each_with_object_driver = _enum_driver("each_with_object")
include_driver = jit.JitDriver(greens=[], reds="auto", name="Array#include?")
eq_driver = jit.JitDriver(greens=[], reds="auto", name="Array#==")
eql_driver = jit.JitDriver(greens=[], reds="auto", name="Array#eql?")


def get_enum_scan_location(want, limit, bytecode):
    return "Array#any?/all?/none?/one? %s" % get_each_location(bytecode)


# any?/all?/none?/one? share one scan; a green can't be None, so the
# block-less (pattern or truthiness) form has its own driver.
enum_scan_block_driver = jit.JitDriver(
    greens=["want", "limit", "bytecode"], reds="auto", name="Array#enum_scan",
    get_printable_location=get_enum_scan_location,
)
enum_scan_plain_driver = jit.JitDriver(
    greens=["want", "limit"], reds="auto", name="Array#enum_scan_plain",
)
initialize_driver = _enum_driver("initialize")
detect_driver = _enum_driver("detect")
select_driver = _enum_driver("select")
map_driver = _enum_driver("map")
reject_driver = _enum_driver("reject")
delete_if_driver = _enum_driver("delete_if")
reverse_each_driver = _enum_driver("reverse_each")
flat_map_driver = _enum_driver("flat_map")


# Array#hash was Ruby code (Thread.current.recursion_guard around an each
# with the running value in a closure cell): every element cost a block frame,
# a cell write and boxed arithmetic, and Rails hashes arrays all the time
# (`[self.class, name, value, type].hash` is an attribute's hash). Here the
# loop is either unrolled into the caller's trace (a fresh array literal) or
# a loop of its own.
hash_driver = jit.JitDriver(greens=[], reds="auto", name="Array#hash")
uniq_block_driver = jit.JitDriver(
    greens=["bytecode"], reds="auto", name="Array#uniq!{}",
    get_printable_location=get_each_location)
uniq_plain_driver = jit.JitDriver(greens=[], reds="auto", name="Array#uniq!")

HASH_SEED = 0x345678
HASH_MULT = 1000003


def hash_step(space, res, w_item):
    w_hash = space.send(w_item, "hash")
    if isinstance(w_hash, W_FixnumObject):
        h = w_hash.intvalue
    elif isinstance(w_hash, W_BignumObject):
        h = w_hash.intmask_w(space)
    else:
        h = space.int_w(w_hash)
    return intmask(r_uint(HASH_MULT) * r_uint(res)) ^ h


@specialize.arg(3)
def item_equal(space, w_a, w_b, name):
    if w_a is w_b:
        return True
    return space.is_true(space.send(w_a, name, [w_b]))


class RubySorter(BaseRubySorter):
    def __init__(self, space, list, listlength=None, sortblock=None):
        BaseRubySorter.__init__(self, list, listlength=listlength)
        self.space = space
        self.sortblock = sortblock

    def lt(self, w_a, w_b):
        w_cmp_res = self.space.compare(w_a, w_b, self.sortblock)
        if self.space.is_kind_of(w_cmp_res, self.space.w_bignum):
            return self.space.bigint_w(w_cmp_res).lt(rbigint.fromint(0))
        else:
            return Coerce.bool(self.space, self.space.send(w_cmp_res, "<", [self.space.newint(0)]))


class RubySortBy(BaseRubySortBy):
    def __init__(self, space, list, listlength=None, sortblock=None):
        BaseRubySortBy.__init__(self, list, listlength=listlength)
        self.space = space
        self.sortblock = sortblock

    def lt(self, w_a, w_b):
        w_cmp_res = self.space.compare(
            self.space.invoke_block(self.sortblock, [w_a]),
            self.space.invoke_block(self.sortblock, [w_b])
        )
        return self.space.int_w(w_cmp_res) < 0


class W_ArrayObject(W_Object):
    classdef = ClassDef("Array", W_Object.classdef)
    classdef.include_module(Enumerable)

    def __init__(self, space, items_w, klass=None):
        W_Object.__init__(self, space, klass)
        self.items_w = items_w

    def __deepcopy__(self, memo):
        obj = super(W_ArrayObject, self).__deepcopy__(memo)
        obj.items_w = copy.deepcopy(self.items_w, memo)
        return obj

    def listview(self, space):
        return self.items_w

    def length(self):
        return len(self.items_w)

    @classdef.singleton_method("allocate")
    def singleton_method_allocate(self, space):
        return W_ArrayObject(space, [], self)

    @classdef.method("initialize")
    @check_frozen()
    def method_initialize(self, space, w_size=None, w_obj=None, block=None):
        """Array.new, Array.new(size, obj = nil), Array.new(array) and
        Array.new(size) { |i| }; a block supersedes obj.

        No loops here, so the JIT inlines it and an Array.new whose
        result does not escape stays virtual; the block form's loop has
        its own driver."""
        if self.items_w:
            del self.items_w[:]
        if w_size is None:
            return self
        if w_obj is None:
            w_ary = space.convert_type(w_size, space.w_array, "to_ary", raise_error=False)
            if w_ary is not space.w_nil:
                self.items_w = space.listview(w_ary)[:]
                return self
        length = space.int_w(space.convert_type(w_size, space.w_fixnum, "to_int"))
        if length < 0:
            raise space.error(space.w_ArgumentError, "negative array size")
        if block is not None:
            self._fill_with_block(space, length, block)
        else:
            if w_obj is None:
                w_obj = space.w_nil
            self.items_w = [w_obj] * length
        return self

    def _fill_with_block(self, space, length, block):
        bytecode = block.bytecode
        i = 0
        while i < length:
            initialize_driver.jit_merge_point(bytecode=bytecode)
            self.items_w.append(space.invoke_block(block, [space.newint(i)]))
            i += 1

    @classdef.method("initialize_copy", other_w="array")
    @classdef.method("replace", other_w="array")
    @check_frozen()
    def method_replace(self, space, other_w):
        del self.items_w[:]
        self.items_w.extend(other_w)
        return self

    @classdef.method("[]")
    @classdef.method("slice")
    def method_subscript(self, space, w_idx, w_count=None):
        start, end, as_range, nil = space.subscript_access(self.length(), w_idx, w_count=w_count)
        if nil:
            return space.w_nil
        elif as_range:
            assert start >= 0
            assert end >= 0
            return W_ArrayObject(space, self.items_w[start:end], space.getnonsingletonclass(self))
        else:
            return self.items_w[start]

    @classdef.method("[]=")
    @check_frozen()
    def method_subscript_assign(self, space, w_idx, w_count_or_obj, w_obj=None):
        w_count = None
        if w_obj:
            w_count = w_count_or_obj
        else:
            w_obj = w_count_or_obj
        start, end, as_range, _ = space.subscript_access(self.length(), w_idx, w_count=w_count)

        if w_count and end < start:
            raise space.error(
                space.w_IndexError,
                "negative length (%d)" % (end - start)
            )
        elif start < 0:
            raise space.error(
                space.w_IndexError,
                "index %d too small for array; minimum: %d" % (
                    start - self.length(),
                    -self.length()
                )
            )
        elif as_range:
            w_converted = space.convert_type(w_obj, space.w_array, "to_ary", raise_error=False)
            if w_converted is space.w_nil:
                rep_w = [w_obj]
            else:
                rep_w = space.listview(w_converted)
            self._subscript_assign_range(space, start, end, rep_w)
        elif start >= self.length():
            self.items_w += [space.w_nil] * (start - self.length() + 1)
            self.items_w[start] = w_obj
        else:
            self.items_w[start] = w_obj
        return w_obj

    def _subscript_assign_range(self, space, start, end, rep_w):
        assert end >= 0
        delta = (end - start) - len(rep_w)
        if delta < 0:
            self.items_w += [None] * -delta
            lim = start + len(rep_w)
            i = self.length() - 1
            while i >= lim:
                self.items_w[i] = self.items_w[i + delta]
                i -= 1
        elif delta > 0:
            del self.items_w[start:start + delta]
        self.items_w[start:start + len(rep_w)] = rep_w

    @classdef.method("slice!")
    @check_frozen()
    def method_slice_i(self, space, w_idx, w_count=None):
        start, end, as_range, nil = space.subscript_access(self.length(), w_idx, w_count=w_count)

        if nil:
            return space.w_nil
        elif as_range:
            start = min(max(start, 0), self.length())
            end = min(max(end, 0), self.length())
            delta = (end - start)
            assert delta >= 0
            w_items = self.items_w[start:start + delta]
            del self.items_w[start:start + delta]
            return space.newarray(w_items)
        else:
            w_item = self.items_w[start]
            del self.items_w[start]
            return w_item

    @classdef.method("size")
    @classdef.method("length")
    def method_length(self, space):
        return space.newint(self.length())

    @classdef.method("empty?")
    def method_emptyp(self, space):
        return space.newbool(self.length() == 0)

    @classdef.method("+", other="array")
    def method_add(self, space, other):
        return space.newarray(self.items_w + other)

    @classdef.method("<<")
    @check_frozen()
    def method_lshift(self, space, w_obj):
        self.items_w.append(w_obj)
        return self

    @classdef.method("concat", other="array")
    @check_frozen()
    def method_concat(self, space, other):
        self.items_w += other
        return self

    @classdef.method("*")
    def method_times(self, space, w_other):
        if space.respond_to(w_other, "to_str"):
            return space.send(self, "join", [w_other])
        n = space.int_w(space.convert_type(w_other, space.w_fixnum, "to_int"))
        if n < 0:
            raise space.error(space.w_ArgumentError, "Count cannot be negative")
        w_res = W_ArrayObject(space, self.items_w * n, space.getnonsingletonclass(self))
        space.infect(w_res, self, freeze=False)
        return w_res

    @classdef.method("insert", w_idx="int")
    @check_frozen()
    def method_insert(self, space, w_idx, args_w):
        if len(args_w) == 0:
            return self

        if isinstance(w_idx, W_FixnumObject):
            idx = space.int_w(w_idx)
        else:
            idx = space.int_w(space.convert_type(w_idx, space.w_fixnum, "to_int"))

        length = len(self.items_w)

        if idx < -length - 1:
            raise space.error(
                space.w_IndexError,
                "index %d too small for array; minimum: %d" % (
                    idx + 1,
                    -length
                )
            )
        elif idx > length:
            before = self.items_w
            for i in range(idx - length):
                before.append(space.w_nil)
            after = []
        elif idx == 0:
            before = []
            after = self.items_w
        elif idx < 0:
            split_idx = length + idx + 1
            assert split_idx >= 0
            before = self.items_w[:split_idx]
            after = self.items_w[split_idx:]
        else:
            assert idx > 0
            before = self.items_w[:idx]
            after = self.items_w[idx:]

        self.items_w = before + args_w + after
        return self

    @classdef.method("push")
    @check_frozen()
    def method_push(self, space, args_w):
        self.items_w.extend(args_w)
        return self

    @classdef.method("shift")
    @check_frozen()
    def method_shift(self, space, w_n=None):
        if w_n is None:
            if self.items_w:
                return self.items_w.pop(0)
            else:
                return space.w_nil
        n = space.int_w(space.convert_type(w_n, space.w_fixnum, "to_int"))
        if n < 0:
            raise space.error(space.w_ArgumentError, "negative array size")
        items_w = self.items_w[:n]
        del self.items_w[:n]
        return space.newarray(items_w)

    @classdef.method("unshift")
    @check_frozen()
    def method_unshift(self, space, args_w):
        for w_obj in reversed(args_w):
            self.items_w.insert(0, w_obj)
        return self

    @classdef.method("join")
    def method_join(self, space, w_sep=None):
        if not self.items_w:
            return space.newstr_fromstr("")
        if w_sep is None or w_sep is space.w_nil:
            separator = ""
        elif space.respond_to(w_sep, "to_str"):
            separator = space.str_w(space.send(w_sep, "to_str"))
        else:
            raise space.error(
                space.w_TypeError,
                "can't convert %s into String" % space.getclass(w_sep).name
            )
        parts = []
        self._join_into(space, parts, [])
        return space.newstr_fromstr(separator.join(parts))

    def _join_into(self, space, parts, seen_w):
        """Array#join's pieces: nested arrays are joined in place, with the
        same separator."""
        for w_seen in seen_w:
            if w_seen is self:
                raise space.error(space.w_ArgumentError, "recursive array join")
        seen_w.append(self)
        for w_o in self.items_w:
            if space.is_kind_of(w_o, space.w_string):
                parts.append(space.str_w(w_o))
            elif isinstance(w_o, W_ArrayObject):
                w_o._join_into(space, parts, seen_w)
            elif space.respond_to(w_o, "to_str"):
                parts.append(space.str_w(space.send(w_o, "to_str")))
            elif space.respond_to(w_o, "to_ary"):
                w_ary = space.send(w_o, "to_ary")
                if isinstance(w_ary, W_ArrayObject):
                    w_ary._join_into(space, parts, seen_w)
                else:
                    parts.append(space.str_w(space.send(w_o, "to_s")))
            else:
                parts.append(space.str_w(space.send(w_o, "to_s")))
        seen_w.pop()

    @classdef.method("pop")
    @check_frozen()
    def method_pop(self, space, w_num=None):
        if w_num is None:
            if self.items_w:
                return self.items_w.pop()
            else:
                return space.w_nil
        else:
            num = space.int_w(space.convert_type(
                w_num, space.w_fixnum, "to_int"
            ))
            if num < 0:
                raise space.error(space.w_ArgumentError, "negative array size")
            else:
                pop_size = max(0, self.length() - num)
                res_w = self.items_w[pop_size:]
                del self.items_w[pop_size:]
                return space.newarray(res_w)

    @classdef.method("delete_at", idx="int")
    @check_frozen()
    def method_delete_at(self, space, idx):
        if idx < 0:
            idx += self.length()
        if idx < 0 or idx >= self.length():
            return space.w_nil
        else:
            return self.items_w.pop(idx)

    @classdef.method("last")
    def method_last(self, space, w_count=None):
        if w_count is not None:
            count = Coerce.int(space, w_count)
            if count < 0:
                raise space.error(space.w_ArgumentError, "negative array size")
            start = self.length() - count
            if start < 0:
                start = 0
            return space.newarray(self.items_w[start:])

        if self.length() == 0:
            return space.w_nil
        else:
            return self.items_w[self.length() - 1]

    @classdef.method("pack")
    def method_pack(self, space, w_template):
        template = Coerce.str(space, w_template)
        result = RPacker(template, space.listview(self)).operate(space)
        w_result = space.newstr_fromchars(result)
        space.infect(w_result, w_template)
        return w_result

    @classdef.method("to_ary")
    def method_to_ary(self, space):
        return self

    @classdef.method("clear")
    @check_frozen()
    def method_clear(self, space):
        del self.items_w[:]
        return self

    @classdef.method("sort!")
    @check_frozen()
    def method_sort_i(self, space, block):
        RubySorter(space, self.items_w, sortblock=block).sort()
        return self

    @classdef.method("hash")
    def method_hash(self, space):
        if jit.isvirtual(self):
            # Built by this very trace, so nothing else refers to it: it
            # cannot contain itself, and its length is a known constant.
            return space.newint(self._hash_unrolled(space))
        res = HASH_SEED
        ec = space.getexecutioncontext()
        with ec.recursion_guard("array_hash", self) as in_recursion:
            if not in_recursion:
                res = self._hash_loop(space)
        return space.newint(res)

    @jit.unroll_safe
    def _hash_unrolled(self, space):
        res = HASH_SEED
        for w_item in self.items_w:
            res = hash_step(space, res, w_item)
        return res

    def _hash_loop(self, space):
        res = HASH_SEED
        i = 0
        while i < len(self.items_w):
            hash_driver.jit_merge_point()
            res = hash_step(space, res, self.items_w[i])
            i += 1
        return res

    @classdef.method("each")
    def method_each(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("each")])
        bytecode = block.bytecode
        i = 0
        # The length is re-read each time: the block may change the array.
        while i < len(self.items_w):
            each_driver.jit_merge_point(bytecode=bytecode)
            space.invoke_block(block, [self.items_w[i]])
            i += 1
        return self

    @classdef.method("each_with_index")
    def method_each_with_index(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("each_with_index")])
        bytecode = block.bytecode
        i = 0
        while i < len(self.items_w):
            each_with_index_driver.jit_merge_point(bytecode=bytecode)
            space.invoke_block(block, [self.items_w[i], space.newint(i)])
            i += 1
        return self

    @classdef.method("each_with_object")
    def method_each_with_object(self, space, w_memo, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("each_with_object"), w_memo])
        bytecode = block.bytecode
        i = 0
        while i < len(self.items_w):
            each_with_object_driver.jit_merge_point(bytecode=bytecode)
            space.invoke_block(block, [self.items_w[i], w_memo])
            i += 1
        return w_memo

    @classdef.method("==")
    def method_eq(self, space, w_other):
        if self is w_other:
            return space.w_true
        if not isinstance(w_other, W_ArrayObject):
            if space.respond_to(w_other, "to_ary"):
                return space.send(w_other, "==", [self])
            return space.w_false
        return space.newbool(self._items_equal(space, w_other, "==", "array_equals"))

    @classdef.method("eql?")
    def method_eqlp(self, space, w_other):
        if self is w_other:
            return space.w_true
        if not isinstance(w_other, W_ArrayObject):
            return space.w_false
        return space.newbool(self._items_equal(space, w_other, "eql?", "array_eqlp"))

    @specialize.arg(3)
    def _items_equal(self, space, w_other, name, guard):
        if len(self.items_w) != len(w_other.items_w):
            return False
        if jit.isvirtual(self) or jit.isvirtual(w_other):
            # One side was built by this trace, so its length is a known
            # constant and it cannot be part of a cycle: compare unrolled.
            return self._items_equal_unrolled(space, w_other, name)
        ec = space.getexecutioncontext()
        with ec.recursion_guard(guard, self) as in_recursion:
            if in_recursion:
                return True
            return self._items_equal_loop(space, w_other, name)

    @jit.unroll_safe
    @specialize.arg(3)
    def _items_equal_unrolled(self, space, w_other, name):
        for i in range(len(self.items_w)):
            if not item_equal(space, self.items_w[i], w_other.items_w[i], name):
                return False
        return True

    @specialize.arg(3)
    def _items_equal_loop(self, space, w_other, name):
        i = 0
        # Lengths are re-read: a user-defined == may mutate either array.
        while i < len(self.items_w) and i < len(w_other.items_w):
            if name == "==":
                eq_driver.jit_merge_point()
            else:
                eql_driver.jit_merge_point()
            if not item_equal(space, self.items_w[i], w_other.items_w[i], name):
                return False
            i += 1
        return len(self.items_w) == len(w_other.items_w)

    @classdef.method("include?")
    @classdef.method("member?")
    def method_includep(self, space, w_obj):
        i = 0
        while i < len(self.items_w):
            include_driver.jit_merge_point()
            w_item = self.items_w[i]
            if w_item is w_obj or space.is_true(space.send(w_item, "==", [w_obj])):
                return space.w_true
            i += 1
        return space.w_false

    def _enum_scan(self, space, args_w, block, want, limit):
        """Count the elements whose any?/all?/none?/one? test (`pattern === e`,
        `yield e`, or `e` itself) has truthiness `want`, stopping at `limit`."""
        if len(args_w) > 1:
            raise space.error(space.w_ArgumentError,
                "wrong number of arguments (given %d, expected 0..1)" % len(args_w))
        # One jit_merge_point per function.
        if block is not None and len(args_w) == 0:
            return self._enum_scan_block(space, block, want, limit)
        return self._enum_scan_plain(space, args_w, want, limit)

    def _enum_scan_block(self, space, block, want, limit):
        bytecode = block.bytecode
        count = 0
        i = 0
        while i < len(self.items_w):
            enum_scan_block_driver.jit_merge_point(want=want, limit=limit, bytecode=bytecode)
            if space.is_true(space.invoke_block(block, [self.items_w[i]])) == want:
                count += 1
                if count >= limit:
                    return count
            i += 1
        return count

    def _enum_scan_plain(self, space, args_w, want, limit):
        count = 0
        i = 0
        while i < len(self.items_w):
            enum_scan_plain_driver.jit_merge_point(want=want, limit=limit)
            w_item = self.items_w[i]
            if len(args_w) > 0:
                truth = space.is_true(space.send(args_w[0], "===", [w_item]))
            else:
                truth = space.is_true(w_item)
            if truth == want:
                count += 1
                if count >= limit:
                    return count
            i += 1
        return count

    @classdef.method("any?")
    def method_anyp(self, space, args_w, block):
        return space.newbool(self._enum_scan(space, args_w, block, True, 1) > 0)

    @classdef.method("all?")
    def method_allp(self, space, args_w, block):
        return space.newbool(self._enum_scan(space, args_w, block, False, 1) == 0)

    @classdef.method("none?")
    def method_nonep(self, space, args_w, block):
        return space.newbool(self._enum_scan(space, args_w, block, True, 1) == 0)

    @classdef.method("one?")
    def method_onep(self, space, args_w, block):
        return space.newbool(self._enum_scan(space, args_w, block, True, 2) == 1)

    @classdef.method("detect")
    @classdef.method("find")
    def method_detect(self, space, w_ifnone=None, block=None):
        if block is None:
            args_w = [space.newsymbol("detect")]
            if w_ifnone is not None:
                args_w.append(w_ifnone)
            return space.send(self, "enum_for", args_w)
        bytecode = block.bytecode
        i = 0
        while i < len(self.items_w):
            detect_driver.jit_merge_point(bytecode=bytecode)
            w_item = self.items_w[i]
            if space.is_true(space.invoke_block(block, [w_item])):
                return w_item
            i += 1
        if w_ifnone is None or w_ifnone is space.w_nil:
            return space.w_nil
        # Like MRI, ifnone is called whatever it is.
        return space.send(w_ifnone, "call")

    @classdef.method("map")
    @classdef.method("collect")
    def method_map(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("map")])
        bytecode = block.bytecode
        result_w = []
        i = 0
        while i < len(self.items_w):
            map_driver.jit_merge_point(bytecode=bytecode)
            result_w.append(space.invoke_block(block, [self.items_w[i]]))
            i += 1
        return space.newarray(result_w)

    @classdef.method("select")
    @classdef.method("filter")
    @classdef.method("find_all")
    def method_select(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("select")])
        bytecode = block.bytecode
        result_w = []
        i = 0
        while i < len(self.items_w):
            select_driver.jit_merge_point(bytecode=bytecode)
            w_item = self.items_w[i]
            if space.is_true(space.invoke_block(block, [w_item])):
                result_w.append(w_item)
            i += 1
        return space.newarray(result_w)

    @classdef.method("reject")
    def method_reject(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("reject")])
        bytecode = block.bytecode
        result_w = []
        i = 0
        while i < len(self.items_w):
            reject_driver.jit_merge_point(bytecode=bytecode)
            w_item = self.items_w[i]
            if not space.is_true(space.invoke_block(block, [w_item])):
                result_w.append(w_item)
            i += 1
        return space.newarray(result_w)

    @classdef.method("delete_if")
    @check_frozen()
    def method_delete_if(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("delete_if")])
        bytecode = block.bytecode
        kept = 0
        i = 0
        while i < len(self.items_w):
            delete_if_driver.jit_merge_point(bytecode=bytecode)
            w_item = self.items_w[i]
            if not space.is_true(space.invoke_block(block, [w_item])):
                if kept < len(self.items_w):
                    self.items_w[kept] = w_item
                kept += 1
            i += 1
        if kept < len(self.items_w):
            del self.items_w[kept:]
        return self

    def _uniq_into(self, space, block, result_w):
        # Appends the first occurrence of each item (or of each item's
        # block value) to result_w, in order. Membership is Hash
        # membership, i.e. `hash` and `eql?`. One jit_merge_point per
        # function, hence the two helpers.
        w_seen = space.newhash()
        if block is not None:
            self._uniq_block(space, block, w_seen, result_w)
        else:
            self._uniq_plain(space, w_seen, result_w)

    def _uniq_block(self, space, block, w_seen, result_w):
        bytecode = block.bytecode
        i = 0
        while i < len(self.items_w):
            uniq_block_driver.jit_merge_point(bytecode=bytecode)
            w_item = self.items_w[i]
            w_key = space.invoke_block(block, [w_item])
            if not w_seen.strategy.contains(w_seen.dict_storage, w_key):
                w_seen.setitem(w_key, space.w_nil)
                result_w.append(w_item)
            i += 1

    def _uniq_plain(self, space, w_seen, result_w):
        i = 0
        while i < len(self.items_w):
            uniq_plain_driver.jit_merge_point()
            w_item = self.items_w[i]
            if not w_seen.strategy.contains(w_seen.dict_storage, w_item):
                w_seen.setitem(w_item, space.w_nil)
                result_w.append(w_item)
            i += 1

    @classdef.method("uniq!")
    @check_frozen()
    def method_uniq_bang(self, space, block):
        result_w = []
        self._uniq_into(space, block, result_w)
        if len(result_w) == len(self.items_w):
            return space.w_nil
        self.items_w = result_w
        return self

    @classdef.method("uniq")
    def method_uniq(self, space, block):
        result_w = []
        self._uniq_into(space, block, result_w)
        return space.newarray(result_w)

    @classdef.method("reverse_each")
    def method_reverse_each(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("reverse_each")])
        bytecode = block.bytecode
        i = len(self.items_w) - 1
        while i >= 0:
            reverse_each_driver.jit_merge_point(bytecode=bytecode)
            space.invoke_block(block, [self.items_w[i]])
            # The block may have shortened the array.
            if len(self.items_w) < i:
                i = len(self.items_w)
            i -= 1
        return self

    @classdef.method("collect_concat")
    @classdef.method("flat_map")
    def method_flat_map(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("flat_map")])
        bytecode = block.bytecode
        result_w = []
        i = 0
        while i < len(self.items_w):
            flat_map_driver.jit_merge_point(bytecode=bytecode)
            w_res = space.invoke_block(block, [self.items_w[i]])
            w_ary = space.convert_type(w_res, space.w_array, "to_ary", raise_error=False)
            if w_ary is space.w_nil:
                result_w.append(w_res)
            else:
                result_w.extend(space.listview(w_ary))
            i += 1
        return space.newarray(result_w)

    @classdef.method("sort_by!")
    @check_frozen()
    def method_sort_by_i(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("sort_by!")])
        RubySortBy(space, self.items_w, sortblock=block).sort()
        return self

    @classdef.method("reverse!")
    @check_frozen()
    def method_reverse_i(self, space):
        self.items_w.reverse()
        return self

    @classdef.method("rotate!", n="int")
    @check_frozen()
    def method_rotate_i(self, space, n=1):
        length = self.length()
        if length == 0:
            return self
        if abs(n) >= length:
            n %= length
        if n < 0:
            n += length
        if n == 0:
            return self
        assert n >= 0
        self.items_w.extend(self.items_w[:n])
        del self.items_w[:n]
        return self

    @classdef.method("insert", i="int")
    @check_frozen()
    @jit.look_inside_iff(lambda self, space, i, args_w: jit.isconstant(len(args_w)))
    def method_insert(self, space, i, args_w):
        if not args_w:
            return self
        length = self.length()
        if i > length:
            self._append_nils(space, i - length)
            self.items_w.extend(args_w)
            return self
        if i < 0:
            if i < -length - 1:
                raise space.error(space.w_IndexError,
                    "index %d too small for array; minimum: %d" % (i + 1, -length)
                )
            i += length + 1
        assert i >= 0
        for w_e in args_w:
            self.items_w.insert(i, w_e)
            i += 1
        return self

    def _append_nils(self, space, num):
        for _ in xrange(num):
            self.items_w.append(space.w_nil)
