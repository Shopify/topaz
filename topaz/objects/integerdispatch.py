"""Makes Integer own the methods of its hidden fixnum and bignum classes.

Since Ruby 2.4 there is a single Integer class, but Topaz keeps separate
(hidden) classes for machine-word and arbitrary-precision integers so each
representation has its own method table.  To make Integer behave as the
one true class:

* Integer gets a dispatching method for every method name the hidden
  classes define, so `Integer.instance_method(:+)`, `alias_method` and
  `method_defined?` see them (see ObjectSpace.hide_integer_subclasses);
* a method defined on, or removed from, Integer after startup drops the
  hidden classes' own definition of that name, so monkeypatching Integer
  affects every integer (see W_ClassObject.shadow_hidden_subclasses).
"""

import copy

from topaz.objects.bignumobject import W_BignumObject
from topaz.objects.classobject import W_ClassObject
from topaz.objects.functionobject import W_FunctionObject
from topaz.objects.intobject import W_FixnumObject


class W_IntegerDispatchFunction(W_FunctionObject):
    _immutable_fields_ = ["w_fixnum_method", "w_bignum_method"]

    def __init__(self, name, w_class, w_fixnum_method, w_bignum_method,
                 visibility=W_FunctionObject.PUBLIC):
        W_FunctionObject.__init__(self, name, w_class, visibility=visibility)
        self.w_fixnum_method = w_fixnum_method
        self.w_bignum_method = w_bignum_method

    def __deepcopy__(self, memo):
        obj = super(W_IntegerDispatchFunction, self).__deepcopy__(memo)
        obj.w_fixnum_method = copy.deepcopy(self.w_fixnum_method, memo)
        obj.w_bignum_method = copy.deepcopy(self.w_bignum_method, memo)
        return obj

    def _impl(self):
        if self.w_fixnum_method is not None:
            return self.w_fixnum_method
        return self.w_bignum_method

    def call(self, space, w_receiver, args_w, block):
        if isinstance(w_receiver, W_FixnumObject):
            w_method = self.w_fixnum_method
        elif isinstance(w_receiver, W_BignumObject):
            w_method = self.w_bignum_method
        else:
            w_method = None
        if w_method is None:
            # This representation doesn't define the method itself; carry on
            # looking above Integer, as a normal method lookup would.
            w_class = self.w_class
            assert isinstance(w_class, W_ClassObject)
            w_method = w_class.superclass.find_method(space, self.name)
            if w_method is None:
                raise space.undefined_method_error(self.name, w_receiver)
        return w_method.call(space, w_receiver, args_w, block)

    def arity(self, space):
        return self._impl().arity(space)

    def source_location(self, space):
        return self._impl().source_location(space)
