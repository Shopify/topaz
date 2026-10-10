import copy

from rpython.rlib import jit

from topaz.objects.objectobject import W_BaseObject


class SuperContext(object):
    """Ancestor-owned metadata shared by invocations and captured blocks."""
    _immutable_fields_ = ["w_owner", "name", "entry"]

    def __init__(self, w_owner, name, entry=None):
        self.w_owner = w_owner
        self.name = name
        if entry is None and w_owner is not None:
            entry = w_owner.origin_entry
        self.entry = entry

    def resolve(self, space, w_receiver, entry=None):
        if entry is not None and entry.w_module is self.w_owner:
            return entry.get_super_context(self.name)
        from topaz.objects.classobject import W_ClassObject
        # A class has only one origin; normal class calls need no search.
        if self.w_owner is None or isinstance(self.w_owner, W_ClassObject):
            return self
        return space.getclass(w_receiver).resolve_super_context(jit.promote(self))


class W_FunctionObject(W_BaseObject):
    _immutable_fields_ = ["name", "w_class", "visibility?"]

    PUBLIC = 0
    PROTECTED = 1
    PRIVATE = 2
    MODULE_FUNCTION = 3

    def __init__(self, name, w_class=None, visibility=PUBLIC):
        self.name = name
        self.w_class = w_class
        self.visibility = visibility

    def __deepcopy__(self, memo):
        obj = super(W_FunctionObject, self).__deepcopy__(memo)
        obj.name = self.name
        obj.w_class = copy.deepcopy(self.w_class, memo)
        obj.visibility = copy.deepcopy(self.visibility, memo)
        return obj

    def update_visibility(self, visibility):
        self.visibility = visibility

    def with_visibility(self, visibility):
        """Return an independent method entry with another visibility."""
        return W_VisibilityFunction(self, visibility)

    def is_undefined(self):
        return False

    def call_with_super(self, space, w_receiver, args_w, block, entry):
        return self.call(space, w_receiver, args_w, block)

    def arity(self, space):
        return space.newint(0)

    def parameters(self, space):
        # Functions written in RPython take any arguments.
        return space.newarray([space.newarray([space.newsymbol("rest")])])

    def source_location(self, space):
        return space.w_nil


class W_VisibilityFunction(W_FunctionObject):
    _immutable_fields_ = ["method"]

    def __init__(self, method, visibility):
        W_FunctionObject.__init__(self, method.name, method.w_class, visibility)
        self.method = method

    def __deepcopy__(self, memo):
        obj = super(W_VisibilityFunction, self).__deepcopy__(memo)
        obj.method = copy.deepcopy(self.method, memo)
        return obj

    def with_visibility(self, visibility):
        return W_VisibilityFunction(self.method, visibility)

    def call(self, space, w_receiver, args_w, block):
        return self.method.call(space, w_receiver, args_w, block)

    def call_with_super(self, space, w_receiver, args_w, block, entry):
        return self.method.call_with_super(space, w_receiver, args_w, block, entry)

    def arity(self, space):
        return self.method.arity(space)

    def parameters(self, space):
        return self.method.parameters(space)

    def source_location(self, space):
        return self.method.source_location(space)


class W_UserFunction(W_FunctionObject):
    # define_method installs an owned copy of a newly built function.
    # Immutable ownership lets calls to known methods fold the owner
    # without a read-then-write quasi-immutable abort during definition.
    _immutable_fields_ = ["bytecode", "lexical_scope", "super_context"]

    def __init__(self, name, bytecode, lexical_scope, visibility=W_FunctionObject.PUBLIC, super_context=None):
        W_FunctionObject.__init__(self, name, visibility=visibility)
        self.bytecode = bytecode
        self.lexical_scope = lexical_scope
        # The module the method was first defined in (see define_method).
        self.super_context = super_context

    def __deepcopy__(self, memo):
        obj = super(W_UserFunction, self).__deepcopy__(memo)
        obj.bytecode = copy.deepcopy(self.bytecode, memo)
        obj.lexical_scope = copy.deepcopy(self.lexical_scope, memo)
        obj.super_context = copy.deepcopy(self.super_context, memo)
        return obj

    def with_visibility(self, visibility):
        return W_UserFunction(
            self.name, self.bytecode, self.lexical_scope, visibility, self.super_context)

    def with_owner(self, w_owner):
        return W_UserFunction(
            self.name, self.bytecode, self.lexical_scope, self.visibility,
            w_owner.origin_entry.get_super_context(None))

    def call(self, space, w_receiver, args_w, block):
        return self.call_with_super(space, w_receiver, args_w, block, None)

    def call_with_super(self, space, w_receiver, args_w, block, entry):
        frame = space.create_frame(
            self.bytecode,
            w_self=w_receiver,
            lexical_scope=self.lexical_scope,
            block=block,
        )
        context = self.super_context
        if context is not None:
            context = context.resolve(space, w_receiver, entry)
        frame.super_context = context
        with space.getexecutioncontext().visit_frame(frame):
            entry_pc = frame.handle_args(space, self.bytecode, args_w, block)
            return space.execute_frame(frame, self.bytecode, entry_pc)

    def arity(self, space):
        return space.newint(self.bytecode.arity(negative_defaults=True))

    def parameters(self, space):
        return self.bytecode.parameters(space, True)

    def source_location(self, space):
        return space.newarray([
            space.newstr_fromstr(self.bytecode.filepath),
            space.newint(self.bytecode.lineno)
        ])


class W_BuiltinFunction(W_FunctionObject):
    _immutable_fields_ = ["func"]

    def __init__(self, name, w_class, func, visibility=W_FunctionObject.PUBLIC):
        W_FunctionObject.__init__(self, name, w_class, visibility=visibility)
        self.func = func

    def __deepcopy__(self, memo):
        obj = super(W_BuiltinFunction, self).__deepcopy__(memo)
        obj.func = self.func
        return obj

    def with_visibility(self, visibility):
        return W_BuiltinFunction(self.name, self.w_class, self.func, visibility)

    def call(self, space, w_receiver, args_w, block):
        from topaz.frame import BuiltinFrame

        frame = BuiltinFrame(self.name, self.w_class, w_receiver)
        ec = space.getexecutioncontext()
        ec.invoke_trace_proc(space, "c-call", self.name, self.w_class.name)
        with ec.visit_frame(frame):
            w_res = self.func(w_receiver, space, args_w, block)
        ec.invoke_trace_proc(space, "c-return", self.name, self.w_class.name)
        return w_res
