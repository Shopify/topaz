import copy
from collections import OrderedDict

from rpython.rlib import jit
from rpython.rlib.rarithmetic import intmask
from rpython.rlib.objectmodel import r_ordereddict, we_are_translated
from rpython.rlib.rerased import new_static_erasing_pair

from topaz.module import ClassDef, check_frozen
from topaz.modules.enumerable import Enumerable
from topaz.objects.objectobject import W_Object
from topaz.objects.procobject import W_ProcObject
from topaz.objects.symbolobject import W_SymbolObject
from topaz.objects.stringobject import W_StringObject


def untranslated_dict_items(storage, keys):
    """NOT_RPYTHON"""
    # RPython's ordered-dict iterators allow deletion during iteration;
    # the host Python OrderedDict iterator raises RuntimeError instead.
    # Snapshot keys only, so callbacks still see current values and deletions.
    for key in keys:
        try:
            value = storage[key]
        except KeyError:
            continue
        yield key, value


class BaseDictStrategy(object):
    def __init__(self, space):
        self.space = space

    def prepare_key(self, w_hash, w_key):
        pass

    def next_entry(self, iterator, w_hash):
        if self is w_hash.strategy:
            return self.iternext(iterator)
        return self.next_entry_after_transition(iterator, w_hash)

    def next_entry_after_transition(self, iterator, w_hash):
        # An incompatible lookup can change storage without changing the
        # Ruby hash. Iterators created before that must see later updates.
        while True:
            w_key, w_value = self.iternext(iterator)
            try:
                w_value = w_hash.getitem(w_key)
            except KeyError:
                continue
            return w_key, w_value


class TypedDictStrategyMixin(object):
    _mixin_ = True

    def switch_to_object_strategy(self, w_hash):
        strategy = self.space.fromcache(ObjectDictStrategy)
        storage = strategy.get_empty_storage(self.space)
        for w_key, w_value in self.unerase(w_hash.dict_storage).iteritems():
            strategy.setitem(storage, w_key, w_value)
        w_hash.strategy = strategy
        w_hash.dict_storage = storage

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
        data = self.unerase(storage)
        if not we_are_translated():
            return self.iter_erase(untranslated_dict_items(data, data.keys()))
        return self.iter_erase(data.iteritems())

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


class SymbolDictStrategy(BaseDictStrategy, TypedDictStrategyMixin):
    """Interned symbols need no Ruby hash/eql? callbacks.

    Start empty hashes here too, selecting string storage for a first string.
    A non-symbol key in a nonempty hash, including a lookup, falls back to
    the generic strategy: custom objects can equal a symbol.
    This is an implementation detail, not Ruby's compare_by_identity mode.
    """
    erase, unerase = new_static_erasing_pair("SymbolDictStrategy")
    iter_erase, iter_unerase = new_static_erasing_pair("SymbolDictStrategyIterator")

    def get_empty_storage(self, space):
        return self.erase(OrderedDict())

    def wrap(self, w_key):
        return w_key

    def unwrap(self, w_key):
        return w_key

    def prepare_key(self, w_hash, w_key):
        if isinstance(w_key, W_SymbolObject):
            return
        if (not self.bool(w_hash.dict_storage) and
                is_builtin_string(self.space, w_key)):
            strategy = self.space.fromcache(StringDictStrategy)
            w_hash.strategy = strategy
            w_hash.dict_storage = strategy.get_empty_storage(self.space)
            return
        self.switch_to_object_strategy(w_hash)


def is_builtin_string(space, w_key):
    return isinstance(w_key, W_StringObject) and w_key.klass is space.w_string


def string_hash(w_key):
    # Keep these callbacks independent of ObjectSpace.hash_w/eq_w: even an
    # unreachable Ruby-dispatch fallback would make the lookup forcing.
    assert isinstance(w_key, W_StringObject)
    return w_key.strategy.hash(w_key.str_storage)


def string_eq(w_left, w_right):
    assert isinstance(w_left, W_StringObject)
    assert isinstance(w_right, W_StringObject)
    if w_left is w_right:
        return True
    if (w_left.strategy.length(w_left.str_storage) !=
            w_right.strategy.length(w_right.str_storage)):
        return False
    # Compare str/list storage directly, without joining mutable strings.
    return w_left.strategy.compare_affix(w_left.str_storage, w_right, 0)


class StringDictStrategy(BaseDictStrategy, TypedDictStrategyMixin):
    """Wrapped builtin strings, compared by their current storage contents.

    Retain the actual frozen Ruby keys for iteration. Subclasses and custom
    lookup keys need the generic callbacks, including their Ruby eql? calls.
    """
    erase, unerase = new_static_erasing_pair("StringDictStrategy")
    iter_erase, iter_unerase = new_static_erasing_pair("StringDictStrategyIterator")

    def get_empty_storage(self, space):
        return self.erase(r_ordereddict(string_eq, string_hash))

    def wrap(self, w_key):
        return w_key

    def unwrap(self, w_key):
        return w_key

    def prepare_key(self, w_hash, w_key):
        if not is_builtin_string(self.space, w_key):
            self.switch_to_object_strategy(w_hash)


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


def get_reject_location(keep, bytecode):
    return get_each_location(bytecode)


# Greens must be ordered ints before refs.
reject_bang_driver = jit.JitDriver(
    greens=["keep", "bytecode"], reds="auto", name="Hash#reject!",
    get_printable_location=get_reject_location,
)
merge_driver = jit.JitDriver(
    greens=["bytecode"], reds="auto", name="Hash#merge!",
    get_printable_location=get_merge_location,
)
transform_keys_driver = jit.JitDriver(
    greens=["bytecode"], reds="auto", name="Hash#transform_keys",
    get_printable_location=get_each_location,
)
hash_driver = jit.JitDriver(greens=[], reds="auto", name="Hash#hash")


class W_HashObject(W_Object):
    classdef = ClassDef("Hash", W_Object.classdef)
    classdef.include_module(Enumerable)

    def __init__(self, space, klass=None):
        W_Object.__init__(self, space, klass)
        self.strategy = space.fromcache(SymbolDictStrategy)
        self.dict_storage = self.strategy.get_empty_storage(space)
        self.w_default = space.w_nil
        self.default_proc = None
        # Whether this hash holds keyword arguments on their way into a
        # call (`f(k: 1)`, `f(**h)`), as opposed to an ordinary hash passed
        # as a positional argument (`f({k: 1})`). See Frame.handle_args.
        self.is_keywords = False

    def __deepcopy__(self, memo):
        obj = super(W_HashObject, self).__deepcopy__(memo)
        obj.strategy = copy.deepcopy(self.strategy, memo)
        obj.dict_storage = self.strategy.copy(self.dict_storage)
        obj.w_default = self.w_default
        obj.default_proc = copy.deepcopy(self.default_proc)
        obj.is_keywords = self.is_keywords
        return obj

    def getitem(self, w_key):
        self.strategy.prepare_key(self, w_key)
        return self.strategy.getitem(self.dict_storage, w_key)

    def setitem(self, w_key, w_value):
        self.strategy.prepare_key(self, w_key)
        return self.strategy.setitem(self.dict_storage, w_key, w_value)

    def delete(self, w_key):
        self.strategy.prepare_key(self, w_key)
        return self.strategy.pop(self.dict_storage, w_key, None)

    def contains(self, w_key):
        self.strategy.prepare_key(self, w_key)
        return self.strategy.contains(self.dict_storage, w_key)

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
                w_key, w_value = strategy.next_entry(iterator, self)
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
                w_key, w_value = strategy.next_entry(iterator, self)
            except StopIteration:
                break
            space.invoke_block(block, [space.newarray([w_key, w_value]), w_memo])
        return w_memo

    def _reject_bang(self, space, block, keep):
        """Deletes the pairs the block drops (keep False: block true means
        delete, as reject!; keep True: block false means delete, as
        select!) as they are visited, so the block sees earlier deletions
        like MRI. Returns whether anything was deleted."""
        bytecode = block.bytecode
        strategy = self.strategy
        iterator = strategy.iteritems(self.dict_storage)
        deleted = False
        while True:
            reject_bang_driver.jit_merge_point(bytecode=bytecode, keep=keep)
            try:
                w_key, w_value = strategy.next_entry(iterator, self)
            except StopIteration:
                break
            if space.is_true(space.invoke_block(block, [w_key, w_value])) != keep:
                self.delete(w_key)
                deleted = True
        return deleted

    def _check_frozen(self, space):
        if space.is_true(self.get_flag(space, "frozen?")):
            raise space.frozen_error(self)

    @classdef.method("reject!")
    def method_reject_bang(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("reject!")])
        self._check_frozen(space)
        if self._reject_bang(space, block, False):
            return self
        return space.w_nil

    @classdef.method("delete_if")
    def method_delete_if(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("delete_if")])
        self._check_frozen(space)
        self._reject_bang(space, block, False)
        return self

    @classdef.method("select!")
    @classdef.method("filter!")
    def method_select_bang(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("select!")])
        self._check_frozen(space)
        if self._reject_bang(space, block, True):
            return self
        return space.w_nil

    @classdef.method("keep_if")
    def method_keep_if(self, space, block):
        if block is None:
            return space.send(self, "enum_for", [space.newsymbol("keep_if")])
        self._check_frozen(space)
        self._reject_bang(space, block, True)
        return self

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
                w_key, w_value = strategy.next_entry(iterator, w_other)
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
                w_key, w_value = strategy.next_entry(iterator, w_other)
            except StopIteration:
                break
            if self.contains(w_key):
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
                w_key, w_value = strategy.next_entry(iterator, self)
            except StopIteration:
                break
            pair = intmask(space.hash_w(w_key) * 1000003) ^ space.hash_w(w_value)
            result = intmask(result + pair)
        return space.newint(result)

    @classdef.method("transform_keys")
    def method_transform_keys(self, space, w_mapping=None, block=None):
        if block is None and w_mapping is None:
            return space.send(self, "enum_for", [space.newsymbol("transform_keys")])
        if w_mapping is not None:
            w_mapping = space.convert_type(w_mapping, space.w_hash, "to_hash")
            assert isinstance(w_mapping, W_HashObject)
        w_result = space.newhash()
        if block is None:
            self._transform_keys_mapping(space, w_mapping, w_result)
        else:
            self._transform_keys_block(space, w_mapping, block, w_result)
        return w_result

    def _transform_keys_mapping(self, space, w_mapping, w_result):
        strategy = self.strategy
        iterator = strategy.iteritems(self.dict_storage)
        while True:
            try:
                w_key, w_value = strategy.next_entry(iterator, self)
            except StopIteration:
                break
            if w_mapping.contains(w_key):
                w_key = w_mapping.getitem(w_key)
            w_result.method_subscript_assign(space, w_key, w_value)

    def _transform_keys_block(self, space, w_mapping, block, w_result):
        bytecode = block.bytecode
        strategy = self.strategy
        iterator = strategy.iteritems(self.dict_storage)
        while True:
            transform_keys_driver.jit_merge_point(bytecode=bytecode)
            try:
                w_key, w_value = strategy.next_entry(iterator, self)
            except StopIteration:
                break
            if (w_mapping is not None and
                    w_mapping.contains(w_key)):
                w_key = w_mapping.getitem(w_key)
            else:
                w_key = space.invoke_block(block, [w_key])
            w_result.method_subscript_assign(space, w_key, w_value)

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
        return space.newbool(self.contains(w_key))


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
        self.w_hash = w_obj
        self.strategy = w_obj.strategy
        self.iterator = self.strategy.iteritems(w_obj.dict_storage)
        return self

    @classdef.method("next")
    def method_next(self, space):
        try:
            w_k, w_v = self.strategy.next_entry(self.iterator, self.w_hash)
        except StopIteration:
            raise space.error(space.w_StopIteration)
        return space.newarray([w_k, w_v])
