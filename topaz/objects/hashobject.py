import copy
from collections import OrderedDict

from rpython.rlib import jit
from rpython.rlib.rarithmetic import intmask
from rpython.rlib.objectmodel import r_ordereddict
from rpython.rlib.rerased import new_static_erasing_pair

from topaz.module import ClassDef, check_frozen
from topaz.modules.enumerable import Enumerable
from topaz.objects.objectobject import W_Object
from topaz.objects.procobject import W_ProcObject


class BaseDictStrategy(object):
    def __init__(self, space):
        pass


class TypedDictStrategyMixin(object):
    _mixin_ = True

    def getitem(self, storage, w_key):
        return self.wrap(self.unerase(storage)[w_key])

    def setitem(self, storage, w_key, w_value):
        self.unerase(storage)[self.unwrap(w_key)] = w_value

    def contains(self, storage, w_key):
        return self.unwrap(w_key) in self.unerase(storage)

    def copy(self, storage):
        return self.erase(self.unerase(storage).copy())

    def clear(self, storage):
        self.unerase(storage).clear()

    def len(self, storage):
        return len(self.unerase(storage))

    def bool(self, storage):
        return bool(self.unerase(storage))

    def pop(self, storage, w_key, default):
        key = self.unwrap(w_key)
        r_dict = self.unerase(storage)
        w_return = r_dict.get(key, default)
        try:
            del r_dict[key]
        except KeyError:
            pass
        return w_return

    def popitem(self, storage):
        key, value = self.unerase(storage).popitem()
        return self.wrap(key), value

    def keys(self, storage):
        return [self.wrap(k) for k in self.unerase(storage).keys()]

    def values(self, storage):
        return self.unerase(storage).values()

    def iteritems(self, storage):
        return self.iter_erase(self.unerase(storage).iteritems())

    def iternext(self, storage):
        key, value = self.iter_unerase(storage).next()
        return self.wrap(key), value


class ObjectDictStrategy(BaseDictStrategy, TypedDictStrategyMixin):
    erase, unerase = new_static_erasing_pair("ObjectDictStrategy")
    iter_erase, iter_unerase = new_static_erasing_pair("ObjectDictStrategyIterator")

    def get_empty_storage(self, space):
        return self.erase(r_ordereddict(space.eq_w, space.hash_w))

    def wrap(self, w_key):
        return w_key

    def unwrap(self, w_key):
        return w_key


class IdentityDictStrategy(BaseDictStrategy, TypedDictStrategyMixin):
    erase, unerase = new_static_erasing_pair("IdentityDictStrategy")
    iter_erase, iter_unerase = new_static_erasing_pair("IdentityDictStrategyIterator")

    def get_empty_storage(self, space):
        return self.erase(OrderedDict())

    def wrap(self, w_key):
        return w_key

    def unwrap(self, w_key):
        return w_key


def get_each_location(bytecode):
    return "Hash#each %s:%d:in %s" % (
        bytecode.filepath, bytecode.lineno, bytecode.name)


def get_merge_location(bytecode):
    return "Hash#merge! %s:%d:in %s" % (
        bytecode.filepath, bytecode.lineno, bytecode.name)


# Their own loops for the JIT, as Array#each has (see arrayobject.py): in
# Ruby, each was an iterator loop ended by a StopIteration, and merge! was
# an each with a block, and both were inlined whole into every trace that
# iterated a hash, which made the traces of Rails code too long to compile.
each_driver = jit.JitDriver(
    greens=["bytecode"], reds="auto", name="Hash#each",
    get_printable_location=get_each_location,
)
each_with_object_driver = jit.JitDriver(
    greens=["bytecode"], reds="auto", name="Hash#each_with_object",
    get_printable_location=get_each_location,
)
merge_driver = jit.JitDriver(
    greens=["bytecode"], reds="auto", name="Hash#merge!",
    get_printable_location=get_merge_location,
)
hash_driver = jit.JitDriver(greens=[], reds="auto", name="Hash#hash")


class W_HashObject(W_Object):
    classdef = ClassDef("Hash", W_Object.classdef)
    classdef.include_module(Enumerable)

    def __init__(self, space, klass=None):
        W_Object.__init__(self, space, klass)
        self.strategy = space.fromcache(ObjectDictStrategy)
        self.dict_storage = self.strategy.get_empty_storage(space)
        self.w_default = space.w_nil
        self.default_proc = None
        # Whether this hash holds keyword arguments on their way into a
        # call (`f(k: 1)`, `f(**h)`), as opposed to an ordinary hash passed
        # as a positional argument (`f({k: 1})`). See Frame.handle_args.
        self.is_keywords = False

    def __deepcopy__(self, memo):
        obj = super(W_HashObject, self).__deepcopy__(memo)
        obj.strategy = copy.deepcopy(self.strategy)
        obj.dict_storage = self.strategy.copy(self.dict_storage)
        obj.w_default = self.w_default
        obj.default_proc = copy.deepcopy(self.default_proc)
        obj.is_keywords = self.is_keywords
        return obj

    def getitem(self, w_key):
        return self.strategy.getitem(self.dict_storage, w_key)

    def setitem(self, w_key, w_value):
        return self.strategy.setitem(self.dict_storage, w_key, w_value)

    def delete(self, w_key):
        return self.strategy.pop(self.dict_storage, w_key, None)

    def is_empty_keywords(self):
        return self.is_keywords and self.size() == 0

    def copy_keywords(self, space):
        """A plain copy, for binding keyword arguments to parameters."""
        w_hash = W_HashObject(space)
        w_hash.strategy = self.strategy
        w_hash.dict_storage = self.strategy.copy(self.dict_storage)
        return w_hash

    def size(self):
        return self.strategy.len(self.dict_storage)

    @classdef.singleton_method("allocate")
    def method_allocate(self, space):
        return W_HashObject(space, self)

    @classdef.method("initialize")
    @check_frozen()
    def method_initialize(self, space, w_default=None, block=None):
        if w_default is not None:
            if block is not None:
                raise space.error(space.w_ArgumentError, "wrong number of arguments")
            self.w_default = w_default
        if block is not None:
            self.default_proc = block
        return self

    @classdef.method("default")
    def method_default(self, space, w_key=None):
        if self.default_proc is not None and w_key is not None:
            return space.invoke_block(self.default_proc, [self, w_key])
        else:
            return self.w_default

    @classdef.method("default=")
    @check_frozen()
    def method_set_default(self, space, w_defl):
        self.default_proc = None
        self.w_default = w_defl

    @classdef.method("default_proc")
    def method_default_proc(self, space):
        if self.default_proc is None:
            return space.w_nil
        return self.default_proc

    @classdef.method("default_proc=")
    def method_set_default_proc(self, space, w_proc):
        w_new_proc = space.convert_type(w_proc, space.w_proc, "to_proc")
        assert isinstance(w_new_proc, W_ProcObject)
        arity = space.int_w(space.send(w_new_proc, "arity"))
        if arity != 2 and space.is_true(space.send(w_new_proc, "lambda?")):
            raise space.error(space.w_TypeError, "default_proc takes two arguments (2 for %s)" % arity)
        self.default_proc = w_new_proc
        self.w_default = space.w_nil
        return w_proc

    @classdef.method("compare_by_identity")
    @check_frozen()
    def method_compare_by_identity(self, space):
        strategy = space.fromcache(IdentityDictStrategy)
        storage = strategy.get_empty_storage(space)

        iter = self.strategy.iteritems(self.dict_storage)
        while True:
            try:
                w_key, w_value = self.strategy.iternext(iter)
            except StopIteration:
                break
            strategy.setitem(storage, w_key, w_value)
        self.strategy = strategy
        self.dict_storage = storage
        return self

    @classdef.method("compare_by_identity?")
    def method_compare_by_identityp(self, space):
        return space.newbool(self.strategy is space.fromcache(IdentityDictStrategy))

    @classdef.method("rehash")
    @check_frozen()
    def method_rehash(self, space):
        storage = self.strategy.get_empty_storage(space)

        iter = self.strategy.iteritems(self.dict_storage)
        while True:
            try:
                w_key, w_value = self.strategy.iternext(iter)
            except StopIteration:
                break
            self.strategy.setitem(storage, w_key, w_value)
        self.dict_storage = storage
        return self

    @classdef.method("[]")
    def method_subscript(self, space, w_key):
        try:
            return self.getitem(w_key)
        except KeyError:
            return space.send(self, "default", [w_key])

    @classdef.method("fetch")
    def method_fetch(self, space, w_key, w_value=None, block=None):
        try:
            return self.getitem(w_key)
        except KeyError:
            if block is not None:
                return space.invoke_block(block, [w_key])
            elif w_value is not None:
                return w_value
            else:
                raise space.error(space.w_KeyError, "key not found: %s" % space.send(w_key, "inspect"))

    @classdef.method("store")
    @classdef.method("[]=")
    @check_frozen()
    def method_subscript_assign(self, space, w_key, w_value):
        # String keys are copied and frozen, unless the hash compares keys
        # by identity.
        if (space.is_kind_of(w_key, space.w_string) and
            self.strategy is not space.fromcache(IdentityDictStrategy) and
            not space.is_true(space.send(w_key, "frozen?"))):

            w_key = space.send(w_key, "dup")
            w_key = space.send(w_key, "freeze")
        self.setitem(w_key, w_value)
        return w_value

    @classdef.method("length")
    @classdef.method("size")
    def method_size(self, space):
        return space.newint(self.size())

    @classdef.method("empty?")
    def method_emptyp(self, space):
        return space.newbool(not self.strategy.bool(self.dict_storage))

    @classdef.method("delete")
    @check_frozen()
    def method_delete(self, space, w_key, block):
        w_res = self.delete(w_key)
        if w_res is None:
            if block:
                return space.invoke_block(block, [w_key])
            w_res = space.w_nil
        return w_res

    @classdef.method("clear")
    @check_frozen()
    def method_clear(self, space):
        self.strategy.clear(self.dict_storage)
        return self

    @classdef.method("shift")
    @check_frozen()
    def method_shift(self, space):
        if not self.strategy.bool(self.dict_storage):
            return space.send(self, "default", [space.w_nil])
        w_key, w_value = self.strategy.popitem(self.dict_storage)
        return space.newarray([w_key, w_value])

    @classdef.method("initialize_copy")
    @classdef.method("replace")
    @check_frozen()
    def method_replace(self, space, w_hash):
        w_hash = space.convert_type(w_hash, space.w_hash, "to_hash")
        assert isinstance(w_hash, W_HashObject)
        self.strategy = w_hash.strategy
        self.dict_storage = self.strategy.copy(w_hash.dict_storage)
        self.w_default = w_hash.w_default
        self.default_proc = w_hash.default_proc
        return self

    @classdef.method("each_pair")
    @classdef.method("each")
    def method_each(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("each")])
        bytecode = block.bytecode
        strategy = self.strategy
        iterator = strategy.iteritems(self.dict_storage)
        while True:
            each_driver.jit_merge_point(bytecode=bytecode)
            try:
                w_key, w_value = strategy.iternext(iterator)
            except StopIteration:
                break
            space.invoke_block(block, [space.newarray([w_key, w_value])])
        return self

    # Enumerable#each_with_object goes through each_entry, which re-splats
    # every pair into a fresh array in a second block frame.
    @classdef.method("each_with_object")
    def method_each_with_object(self, space, w_memo, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("each_with_object"), w_memo])
        bytecode = block.bytecode
        strategy = self.strategy
        iterator = strategy.iteritems(self.dict_storage)
        while True:
            each_with_object_driver.jit_merge_point(bytecode=bytecode)
            try:
                w_key, w_value = strategy.iternext(iterator)
            except StopIteration:
                break
            space.invoke_block(block, [space.newarray([w_key, w_value]), w_memo])
        return w_memo

    @classdef.method("update")
    @classdef.method("merge!")
    @check_frozen()
    def method_merge_i(self, space, w_other, block):
        w_other = space.convert_type(w_other, space.w_hash, "to_hash")
        assert isinstance(w_other, W_HashObject)
        if block is None:
            self._merge_from(space, w_other)
        else:
            self._merge_from_with_block(space, w_other, block)
        return self

    def _merge_from(self, space, w_other):
        strategy = w_other.strategy
        iterator = strategy.iteritems(w_other.dict_storage)
        while True:
            try:
                w_key, w_value = strategy.iternext(iterator)
            except StopIteration:
                break
            self.method_subscript_assign(space, w_key, w_value)

    def _merge_from_with_block(self, space, w_other, block):
        bytecode = block.bytecode
        strategy = w_other.strategy
        iterator = strategy.iteritems(w_other.dict_storage)
        while True:
            merge_driver.jit_merge_point(bytecode=bytecode)
            try:
                w_key, w_value = strategy.iternext(iterator)
            except StopIteration:
                break
            if self.strategy.contains(self.dict_storage, w_key):
                w_value = space.invoke_block(
                    block, [w_key, self.getitem(w_key), w_value])
            self.method_subscript_assign(space, w_key, w_value)

    @classdef.method("hash")
    def method_hash(self, space):
        # Equal hashes have equal hash values, whatever their insertion
        # order, so the pair hashes are summed. In Ruby this built a
        # [key, value] array per pair and hashed that.
        strategy = self.strategy
        result = strategy.len(self.dict_storage)
        iterator = strategy.iteritems(self.dict_storage)
        while True:
            hash_driver.jit_merge_point()
            try:
                w_key, w_value = strategy.iternext(iterator)
            except StopIteration:
                break
            pair = intmask(space.hash_w(w_key) * 1000003) ^ space.hash_w(w_value)
            result = intmask(result + pair)
        return space.newint(result)

    @classdef.method("merge")
    def method_merge(self, space, w_other, block):
        w_copy = space.send(self, "dup")
        assert isinstance(w_copy, W_HashObject)
        return w_copy.method_merge_i(space, w_other, block)

    @classdef.method("keys")
    def method_keys(self, space):
        return space.newarray(self.strategy.keys(self.dict_storage))

    @classdef.method("values")
    def method_values(self, space):
        return space.newarray(self.strategy.values(self.dict_storage))

    @classdef.method("to_hash")
    def method_to_hash(self, space):
        return self

    @classdef.method("key?")
    @classdef.method("has_key?")
    @classdef.method("member?")
    @classdef.method("include?")
    def method_includep(self, space, w_key):
        return space.newbool(self.strategy.contains(self.dict_storage, w_key))


class W_HashIterator(W_Object):
    classdef = ClassDef("HashIterator", W_Object.classdef)

    def __init__(self, space):
        W_Object.__init__(self, space)

    @classdef.singleton_method("allocate")
    def method_allocate(self, space):
        return W_HashIterator(space)

    @classdef.method("initialize")
    def method_initialize(self, w_obj):
        assert isinstance(w_obj, W_HashObject)
        self.strategy = w_obj.strategy
        self.iterator = self.strategy.iteritems(w_obj.dict_storage)
        return self

    @classdef.method("next")
    def method_next(self, space):
        try:
            w_k, w_v = self.strategy.iternext(self.iterator)
        except StopIteration:
            raise space.error(space.w_StopIteration)
        return space.newarray([w_k, w_v])
