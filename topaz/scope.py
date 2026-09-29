import copy


class StaticScope(object):
    _immutable_fields_ = ["w_mod", "backscope", "w_singleton_of"]

    def __init__(self, w_mod, backscope, w_singleton_of=None):
        self.w_mod = w_mod
        self.backscope = backscope
        # For instance_exec on an object without a singleton class: `def`
        # defines on the object's singleton class, made only when needed;
        # w_mod is the object's class meanwhile.
        self.w_singleton_of = w_singleton_of

    def __deepcopy__(self, memo):
        return StaticScope(
            copy.deepcopy(self.w_mod, memo),
            copy.deepcopy(self.backscope, memo),
            copy.deepcopy(self.w_singleton_of, memo))
