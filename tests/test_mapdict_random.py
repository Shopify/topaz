"""Model-based storage tests, independent of the inline/array layout."""

import copy
import struct
import sys

import pytest

pytest.importorskip("hypothesis")
from hypothesis import example, given, settings, strategies as st

from topaz import mapdict
from topaz.objects.floatobject import W_FloatObject
from topaz.objects.intobject import W_FixnumObject
from topaz.objects.objectobject import W_Object, W_Root


ATTRS = ["@a", "@b", "@c", "@d", "@e", "@f"]
FLAGS = ["frozen?", "tainted?", "untrusted?"]


class StorageSpace(object):
    # Exercise real W_Object and mapdict operations without booting Ruby.
    w_fixnum = W_FixnumObject
    w_float = W_FloatObject

    def __init__(self):
        self.cache = {}
        self.w_true = W_Root()
        self.w_false = W_Root()
        self.w_nil = W_Root()

    def fromcache(self, cls):
        if cls not in self.cache:
            self.cache[cls] = cls(self)
        return self.cache[cls]

    def is_kind_of(self, w_value, cls):
        return isinstance(w_value, cls)

    def newint(self, value):
        return W_FixnumObject(self, value)

    def newfloat(self, value):
        return W_FloatObject(self, value)

    def int_w(self, w_value):
        return w_value.intvalue

    def float_w(self, w_value):
        return w_value.floatvalue


def wrap_value(space, value):
    if value is None:
        return space.w_nil
    if isinstance(value, (int, long)):
        return space.newint(int(value))
    if type(value) is float:
        return space.newfloat(value)
    # Distinct references catch accidental aliasing of boxed storage.
    return W_Root()


def check_value(actual, expected):
    if isinstance(expected, W_FixnumObject):
        assert isinstance(actual, W_FixnumObject)
        assert actual.intvalue == expected.intvalue
    elif isinstance(expected, W_FloatObject):
        assert isinstance(actual, W_FloatObject)
        # Also compare NaNs and preserve the sign of zero.
        assert struct.pack("d", actual.floatvalue) == struct.pack("d", expected.floatvalue)
    else:
        assert actual is expected


def run_sequence(sequence):
    space = StorageSpace()
    klass = object()
    objects = [W_Object(space, klass) for _ in range(3)]
    assert objects[0].map is objects[1].map is objects[2].map
    models = [{} for _ in objects]
    flags = [{} for _ in objects]

    for op, index, name, value in sequence:
        obj = objects[index]
        model = models[index]
        if op == "set":
            w_value = wrap_value(space, value)
            obj.set_instance_var(space, name, w_value)
            model[name] = w_value
        elif op == "del":
            removed = obj.remove_instance_var(space, name)
            check_value(removed, model.pop(name, None))
        elif op == "flag":
            if value:
                obj.set_flag(space, name)
            else:
                obj.unset_flag(space, name)
            flags[index][name] = value
        elif op == "copy":
            # Copy attributes into a fresh destination, like the low-level
            # part of dup. Flags are handled separately by Ruby's dup/clone.
            replacement = W_Object(space, klass)
            replacement.copy_instance_vars(space, obj)
            objects[value] = replacement
            models[value] = model.copy()
            flags[value] = {}
        else:
            assert False, op

        # Check untouched objects too: map sharing must not share values.
        for obj, model, expected_flags in zip(objects, models, flags):
            assert obj.getclass(space) is klass
            assert sorted(obj.instance_variable_names(space)) == sorted(model)
            for attr in ATTRS:
                check_value(obj.find_instance_var(space, attr), model.get(attr))
            for flag in FLAGS:
                expected = space.w_true if expected_flags.get(flag, False) else space.w_false
                assert obj.get_flag(space, flag) is expected


values = st.one_of(
    st.none(), st.just("boxed"),
    st.integers(min_value=-sys.maxint - 1, max_value=sys.maxint),
    st.floats(),
)
indices = st.integers(min_value=0, max_value=2)
operations = st.one_of(
    st.tuples(st.just("set"), indices, st.sampled_from(ATTRS), values),
    st.tuples(st.just("del"), indices, st.sampled_from(ATTRS), st.none()),
    st.tuples(st.just("copy"), indices, st.none(), indices),
)
operations_with_flags = st.one_of(
    operations,
    st.tuples(st.just("flag"), indices, st.sampled_from(FLAGS), st.booleans()),
)


@settings(max_examples=200, deadline=None, database=None)
@given(sequence=st.lists(operations, min_size=1, max_size=150))
@example(sequence=[
    ("set", 0, "@a", "boxed"),
    ("set", 0, "@b", None),
    ("set", 0, "@c", "boxed"),
    ("copy", 0, None, 1),
    ("del", 0, "@b", None),
    ("del", 0, "@c", None),
    ("set", 0, "@b", "boxed"),
    ("set", 0, "@c", "boxed"),
    ("set", 0, "@a", 42),
    ("set", 0, "@a", -0.0),
    ("set", 0, "@a", "boxed"),
])
def test_instance_storage_matches_model(sequence):
    run_sequence(sequence)


@settings(max_examples=200, deadline=None, database=None)
@given(sequence=st.lists(operations_with_flags, min_size=1, max_size=150))
@example(sequence=[
    ("set", 0, "@a", None),
    ("flag", 0, "tainted?", True),
    ("del", 0, "@a", None),
])
@example(sequence=[
    ("set", 0, "@a", 42),
    ("flag", 0, "tainted?", True),
    ("flag", 0, "untrusted?", True),
    ("flag", 0, "untrusted?", False),
    ("set", 0, "@b", "boxed"),
    ("set", 0, "@a", "boxed"),
    ("del", 0, "@b", None),
])
def test_instance_storage_with_flags_matches_model(sequence):
    run_sequence(sequence)


def test_inline_storage_spills_and_shrinks():
    space = StorageSpace()
    obj = W_Object(space, object())
    values = [W_Root() for _ in range(3)]
    obj.set_instance_var(space, "@a", values[0])
    obj.set_instance_var(space, "@b", values[1])
    assert obj.map.has_inline_storage()
    assert mapdict.unerase_value(obj.object_storage) is values[0]
    assert mapdict.unerase_value(obj.unboxed_storage) is values[1]

    obj.set_instance_var(space, "@c", values[2])
    assert not obj.map.has_inline_storage()
    assert mapdict.unerase_objects(obj.object_storage)[:3] == values
    obj.remove_instance_var(space, "@a")
    assert obj.map.has_inline_storage()
    assert mapdict.unerase_value(obj.object_storage) is values[1]
    assert mapdict.unerase_value(obj.unboxed_storage) is values[2]

    obj.set_instance_var(space, "@a", space.newint(42))
    assert not obj.map.has_inline_storage()
    assert obj.find_instance_var(space, "@a").intvalue == 42
    obj.remove_instance_var(space, "@a")
    assert obj.map.has_inline_storage()
    assert obj.find_instance_var(space, "@b") is values[1]
    assert obj.find_instance_var(space, "@c") is values[2]
    obj.remove_instance_var(space, "@b")
    assert mapdict.unerase_value(obj.unboxed_storage) is None
    obj.remove_instance_var(space, "@c")
    assert mapdict.unerase_value(obj.object_storage) is None


@pytest.mark.parametrize("kind", ["inline", "boxed_array", "unboxed_array"])
def test_deepcopy_storage(kind):
    space = StorageSpace()
    obj = W_Object(space, object())
    obj.set_instance_var(space, "@a", W_Root())
    obj.set_flag(space, "tainted?")
    if kind == "boxed_array":
        obj.set_instance_var(space, "@b", W_Root())
    elif kind == "unboxed_array":
        obj.set_instance_var(space, "@b", space.newfloat(-0.0))
    memo = {id(space.w_true): space.w_true, id(space.w_false): space.w_false}
    duplicate = copy.deepcopy(obj, memo)
    assert duplicate.instance_variable_names(space) == obj.instance_variable_names(space)
    assert duplicate.get_flag(space, "tainted?") is space.w_true
    assert duplicate.find_instance_var(space, "@a") is not obj.find_instance_var(space, "@a")
    if kind == "unboxed_array":
        check_value(duplicate.find_instance_var(space, "@b"), space.newfloat(-0.0))
    duplicate.remove_instance_var(space, "@a")
    assert obj.find_instance_var(space, "@a") is not None
    assert duplicate.find_instance_var(space, "@a") is None
