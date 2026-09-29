import copy

from rpython.rlib import jit
from rpython.rlib.objectmodel import specialize

from topaz.module import ClassDef
from topaz.objects.moduleobject import UndefMethod, W_ModuleObject
from topaz.objects.objectobject import W_Object


class W_ClassObject(W_ModuleObject):
    _immutable_fields_ = ["superclass?", "is_singleton", "is_hidden?"]

    classdef = ClassDef("Class", W_ModuleObject.classdef)

    def __init__(self, space, name, superclass, is_singleton=False, attached=None):
        W_ModuleObject.__init__(self, space, name)
        self.superclass = superclass
        self.is_singleton = is_singleton
        # Hidden classes are implementation details, like the fixnum and
        # bignum representations of Integer: Kernel#class and friends skip
        # over them to their superclass, as they skip singleton classes.
        self.is_hidden = False
        # Set on a class whose instances are really instances of these hidden
        # subclasses (Integer); see ObjectSpace.hide_integer_subclasses.
        self.hidden_subclasses = None
        self.attached = attached

        if self.superclass is not None:
            # During bootstrap, we cannot create singleton classes, yet. The
            # singleton class comes first: the inherited hook may call the
            # superclass's class methods on the new class.
            if not self.is_singleton and not space.bootstrap:
                self.getsingletonclass(space)
            # A singleton class is not a subclass as far as Ruby code can
            # tell: the inherited hook is not called for it.
            if not self.is_singleton:
                self.superclass.inherited(space, self)

    def __deepcopy__(self, memo):
        obj = super(W_ClassObject, self).__deepcopy__(memo)
        obj.is_singleton = self.is_singleton
        obj.is_hidden = self.is_hidden
        obj.hidden_subclasses = copy.deepcopy(self.hidden_subclasses, memo)
        obj.attached = copy.deepcopy(self.attached, memo)
        obj.superclass = copy.deepcopy(self.superclass, memo)
        return obj

    def shadow_hidden_subclasses(self, name):
        # A method defined on, or removed from, a class with hidden
        # implementation subclasses must take effect for their instances
        # too, so drop those subclasses' own definitions of it.
        if self.hidden_subclasses is not None:
            for w_sub in self.hidden_subclasses:
                if name in w_sub.methods_w:
                    del w_sub.methods_w[name]
                    w_sub.mutated()

    def getsingletonclass(self, space):
        if self.klass is None or not self.klass.is_singleton:
            if self.superclass is None:
                singleton_superclass = space.w_class
            else:
                singleton_superclass = self.superclass.getsingletonclass(space)
            if self.name is None:
                name = None
            else:
                name = "#<Class:%s>" % self.name
            self.klass = space.newclass(
                name, singleton_superclass, is_singleton=True, attached=self
            )
        return self.klass

    def find_const(self, space, name, autoload=True):
        w_res = W_ModuleObject.find_included_const(self, space, name, autoload=autoload)
        if w_res is None and self.superclass is not None:
            w_res = self.superclass.find_const(space, name, autoload=autoload)
        return w_res

    def find_scoped_const(self, space, name, autoload=True):
        # `Klass::Name` looks in the class and its ancestors, but only
        # reaches Object's constants for Object itself.
        w_cls = self
        while w_cls is not None:
            if w_cls is space.w_object and self is not space.w_object:
                return None
            w_res = W_ModuleObject.find_included_const(w_cls, space, name, autoload=autoload)
            if w_res is not None:
                return w_res
            w_cls = w_cls.superclass
        return None

    def inherited_constants(self, space):
        consts = {}
        for const in W_ModuleObject.local_constants(self, space):
            consts[const] = None
        w_cls = self.superclass
        while w_cls is not None:
            for const in w_cls.local_constants(space):
                consts[const] = None
            w_cls = w_cls.superclass

        return consts.keys()

    @jit.unroll_safe
    def find_method_uncached(self, space, name):
        method = W_ModuleObject.find_method_uncached(self, space, name)
        if method is None and self.superclass is not None:
            method = self.superclass.find_method_uncached(space, name)
        return method

    def find_method_super(self, space, name):
        method = W_ModuleObject.find_method_super(self, space, name)
        if method is None and self.superclass is not None:
            method = self.superclass.find_method(space, name)
        return method

    @specialize.argtype(2)
    def methods(self, space, visibility=None, inherit=True):
        methods = {}
        for name in W_ModuleObject.methods(self, space, inherit=inherit, visibility=visibility):
            methods[name] = None
        if inherit and self.superclass is not None:
            for name in self.superclass.methods(space, visibility=visibility):
                method = self._find_method_pure(space, name, self.version)
                if method is None or not isinstance(method, UndefMethod):
                    methods[name] = None
        return methods.keys()

    def ancestors(self, include_singleton=True, include_self=True):
        assert include_self
        ary = W_ModuleObject.ancestors(self,
            include_singleton, not (self.is_singleton and not include_singleton)
        )
        if self.superclass is not None:
            ary += self.superclass.ancestors(include_singleton)
        return ary

    def inherited(self, space, w_mod):
        self.add_descendant(w_mod)
        if not space.bootstrap and space.respond_to(self, "inherited"):
            space.send(self, "inherited", [w_mod])

    def method_removed(self, space, w_name):
        if self.is_singleton:
            space.send(self.attached, "singleton_method_removed", [w_name])
        else:
            W_ModuleObject.method_removed(self, space, w_name)

    def method_added(self, space, w_name):
        if self.is_singleton:
            space.send(self.attached, "singleton_method_added", [w_name])
        else:
            W_ModuleObject.method_added(self, space, w_name)

    def method_undefined(self, space, w_name):
        if self.is_singleton:
            space.send(self.attached, "singleton_method_undefined", [w_name])
        else:
            W_ModuleObject.method_undefined(self, space, w_name)

    @classdef.singleton_method("allocate")
    def singleton_method_allocate(self, space):
        return space.newclass(None, None)

    @classdef.method("new")
    def method_new(self, space, args_w, block):
        w_obj = space.send(self, "allocate")
        space.send(w_obj, "initialize", args_w, block)
        return w_obj

    @classdef.method("allocate")
    def method_allocate(self, space):
        return W_Object(space, self)

    @classdef.method("initialize")
    def method_initialize(self, space, w_superclass=None, block=None):
        if self.superclass is not None or self is space.w_basicobject:
            raise space.error(space.w_TypeError, "already initialized class")
        if w_superclass is not None:
            if not isinstance(w_superclass, W_ClassObject):
                raise space.error(space.w_TypeError,
                    "superclass must be a Class (%s given)" % space.obj_to_s(space.getclass(w_superclass))
                )
            if w_superclass is space.w_class:
                raise space.error(space.w_TypeError,
                    "can't make subclass of Class"
                )
            if w_superclass.is_singleton:
                raise space.error(space.w_TypeError,
                    "can't make subclass of singleton class"
                )
        else:
            w_superclass = space.w_object
        self.superclass = w_superclass
        self.getsingletonclass(space)
        self.superclass.inherited(space, self)
        space.send_super(space.getclassfor(W_ClassObject), self, "initialize", [], block=block)

    @classdef.method("initialize_copy")
    def method_initialize_copy(self, space, w_other):
        if self.superclass is not None or self is space.w_basicobject:
            raise space.error(space.w_TypeError, "already initialized class")
        return space.send_super(space.getclassfor(W_ClassObject), self, "initialize_copy", [w_other])

    @classdef.method("superclass")
    def method_superclass(self, space):
        if self.superclass is not None:
            return self.superclass
        if self is space.w_basicobject:
            return space.w_nil
        raise space.error(space.w_TypeError, "uninitialized class")

    @classdef.method("class_variables", inherit="bool")
    def method_class_variables(self, space, inherit=True):
        names = []
        w_cls = self
        while w_cls is not None:
            for cvar in w_cls.class_variables:
                if cvar not in names:
                    names.append(cvar)
            if not inherit:
                break
            w_cls = w_cls.superclass
        return space.newarray([space.newsymbol(cvar) for cvar in names])

    @classdef.method("subclasses")
    def method_subclasses(self, space):
        subclasses_w = []
        for w_mod in self.descendants_w():
            if (isinstance(w_mod, W_ClassObject) and w_mod.superclass is self and
                    not w_mod.is_singleton and w_mod not in subclasses_w):
                subclasses_w.append(w_mod)
        subclasses_w.reverse()
        return space.newarray(subclasses_w)

    @classdef.method("attached_object")
    def method_attached_object(self, space):
        if not self.is_singleton or self.attached is None:
            raise space.error(space.w_TypeError,
                "'%s' is not a singleton class" % space.obj_to_s(self))
        return self.attached

    @classdef.method("singleton_class?")
    def method_singleton_classp(self, space):
        return space.newbool(self.is_singleton)

    @classdef.method("instance_variables")
    def method_instance_variables(self, space):
        return space.newarray([space.newsymbol(ivar) for ivar in self.instance_variables])
