import copy

from rpython.rlib import jit
from rpython.rlib.objectmodel import specialize

from topaz.celldict import CellDict, VersionTag
from topaz.coerce import Coerce
from topaz.module import ClassDef, check_frozen
from topaz.objects.arrayobject import W_ArrayObject
from topaz.objects.functionobject import W_FunctionObject, W_UserFunction
from topaz.objects.objectobject import W_RootObject
from topaz.objects.procobject import W_ProcObject
from topaz.scope import StaticScope


class AttributeReader(W_FunctionObject):
    _immutable_fields_ = ["varname"]

    def __init__(self, varname):
        W_FunctionObject.__init__(self, varname)
        self.varname = varname

    def __deepcopy__(self, memo):
        obj = super(W_FunctionObject, self).__deepcopy__(memo)
        obj.varname = self.varname
        return obj

    def call(self, space, w_obj, args_w, block):
        return space.find_instance_var(w_obj, self.varname) or space.w_nil


class AttributeWriter(W_FunctionObject):
    _immutable_fields_ = ["varname"]

    def __init__(self, varname):
        W_FunctionObject.__init__(self, varname)
        self.varname = varname

    def __deepcopy__(self, memo):
        obj = super(W_FunctionObject, self).__deepcopy__(memo)
        obj.varname = self.varname
        return obj

    def call(self, space, w_obj, args_w, block):
        [w_value] = args_w
        space.set_instance_var(w_obj, self.varname, w_value)
        return w_value

    def arity(self, space):
        return space.newint(1)


class UndefMethod(W_FunctionObject):
    _immutable_fields_ = ["name"]

    def __init__(self, name):
        W_FunctionObject.__init__(self, name)
        self.name = name

    def is_undefined(self):
        return True

    def call(self, space, w_obj, args_w, block):
        args_w.insert(0, space.newsymbol(self.name))
        return space.send(w_obj, "method_missing", args_w, block)


class DefineMethodBlock(W_FunctionObject):
    _immutable_fields_ = ["name", "block"]

    def __init__(self, name, block):
        W_FunctionObject.__init__(self, name)
        self.name = name
        self.block = block
        self.w_owner = None

    def call(self, space, w_obj, args_w, block):
        from topaz.interpreter import RaiseReturn

        method_block = self.block.copy(space, w_self=w_obj, is_lambda=True)
        if self.w_owner is not None:
            method_block.w_owner = self.w_owner
        try:
            return space.invoke_block(method_block, args_w, block)
        except RaiseReturn as e:
            return e.w_value

    def arity(self, space):
        return space.newint(self.block.bytecode.arity(negative_defaults=True))


class DefineMethodMethod(W_FunctionObject):
    _immutable_fields_ = ["name", "w_unbound_method"]

    def __init__(self, name, w_unbound_method):
        W_FunctionObject.__init__(self, name)
        self.name = name
        self.w_unbound_method = w_unbound_method

    def call(self, space, w_obj, args_w, block):
        w_bound_method = space.send(self.w_unbound_method, "bind", [w_obj])
        return space.send(w_bound_method, "call", args_w, block)


class W_Autoload(W_RootObject):
    def __init__(self, space, path):
        self.space = space
        self.path = path

    def __deepcopy__(self, memo):
        obj = super(W_Autoload, self).__deepcopy__(memo)
        obj.space = copy.deepcopy(self.space, memo)
        obj.path = self.path
        return obj

    def load(self):
        self.space.send(
            self.space.w_kernel,
            "require",
            [self.space.newstr_fromstr(self.path)]
        )


class W_ModuleObject(W_RootObject):
    _immutable_fields_ = ["version?", "included_modules?[*]", "prepended_modules?[*]",
                          "klass?", "name?"]

    classdef = ClassDef("Module", W_RootObject.classdef)

    def __init__(self, space, name, klass=None):
        self.name = name
        self.klass = klass
        self.version = VersionTag()
        self.methods_w = {}
        self.constants_w = {}
        self.class_variables = CellDict()
        self.instance_variables = CellDict()
        self.flags = CellDict()
        self.included_modules = []
        # Modules prepended here, in lookup order (the latest first).
        self.prepended_modules = []
        self.descendants = []

    def __deepcopy__(self, memo):
        obj = super(W_ModuleObject, self).__deepcopy__(memo)
        obj.name = self.name
        obj.klass = copy.deepcopy(self.klass, memo)
        obj.version = copy.deepcopy(self.version, memo)
        obj.methods_w = copy.deepcopy(self.methods_w, memo)
        obj.constants_w = copy.deepcopy(self.constants_w, memo)
        obj.class_variables = copy.deepcopy(self.class_variables, memo)
        obj.instance_variables = copy.deepcopy(self.instance_variables, memo)
        obj.flags = copy.deepcopy(self.flags, memo)
        obj.included_modules = copy.deepcopy(self.included_modules, memo)
        obj.prepended_modules = copy.deepcopy(self.prepended_modules, memo)
        obj.descendants = copy.deepcopy(self.descendants, memo)
        return obj

    def getclass(self, space):
        if self.klass is not None:
            return jit.promote(self).klass
        return W_RootObject.getclass(self, space)

    def getsingletonclass(self, space):
        if self.klass is None or not self.klass.is_singleton:
            self.klass = space.newclass(
                "#<Class:%s>" % self.name, self.klass or space.w_module, is_singleton=True, attached=self
            )
        return self.klass

    def mutated(self):
        self.version = VersionTag()

    def shadow_hidden_subclasses(self, name):
        """Called whenever the method `name` is (re)defined or removed here.
        Overridden by classes with hidden implementation subclasses."""

    def define_method(self, space, name, method):
        if (name == "initialize" or name == "initialize_copy" or
            method.visibility == W_FunctionObject.MODULE_FUNCTION):
            method.update_visibility(W_FunctionObject.PRIVATE)
        self.mutated()
        self.methods_w[name] = method
        if isinstance(method, W_UserFunction):
            if method.w_owner is None:
                method.w_owner = self
        elif isinstance(method, DefineMethodBlock):
            if method.w_owner is None:
                method.w_owner = self
        self.shadow_hidden_subclasses(name)
        if not space.bootstrap:
            if isinstance(method, UndefMethod):
                self.method_undefined(space, space.newsymbol(name))
            else:
                self.method_added(space, space.newsymbol(name))

    @jit.unroll_safe
    def find_method(self, space, name):
        for module in self.prepended_modules:
            method = module.find_local_method(space, name)
            if method is not None:
                return method
        method = self._find_method_pure(space, name, self.version)
        if method is None:
            for module in self.included_modules:
                method = module.find_method(space, name)
                if method is not None:
                    return method
        return method

    def find_local_method(self, space, name):
        return self._find_method_pure(space, name, self.version)

    @jit.unroll_safe
    def find_method_after(self, space, w_owner, name):
        """For super: the method `name` in these ancestors that comes
        after `w_owner`, the module that defines the calling method."""
        ancestors = self.ancestors()
        found = False
        for w_mod in ancestors:
            if found:
                method = w_mod.find_local_method(space, name)
                if method is not None:
                    if isinstance(method, UndefMethod):
                        return None
                    return method
            elif w_mod is w_owner:
                found = True
        if not found:
            return w_owner.find_method_super(space, name)
        return None

    @jit.unroll_safe
    def find_method_super(self, space, name):
        for module in self.included_modules:
            method = module.find_method(space, name)
            if method is not None:
                return method
        return None

    @jit.elidable
    def _find_method_pure(self, space, method, version):
        return self.methods_w.get(method, None)

    @specialize.argtype(2)
    def methods(self, space, visibility=None, inherit=True):
        methods = {}
        for name, method in self.methods_w.iteritems():
            if (not isinstance(method, UndefMethod) and
                (visibility is None or method.visibility == visibility)):
                methods[name] = None

        if inherit:
            for w_mod in self.included_modules:
                for name in w_mod.methods(space, visibility=visibility):
                    method = self._find_method_pure(space, name, self.version)
                    if method is None or not isinstance(method, UndefMethod):
                        methods[name] = None
            for w_mod in self.prepended_modules:
                for name in w_mod.methods(space, visibility=visibility, inherit=False):
                    methods[name] = None
        return methods.keys()

    def set_const(self, space, name, w_obj):
        self.mutated()
        self.constants_w[name] = w_obj
        if isinstance(w_obj, W_ModuleObject) and w_obj.name is None and self.name is not None:
            w_obj.set_name_in_scope(space, name, self)

    def find_const(self, space, name, autoload=True):
        w_res = self.find_included_const(space, name, autoload=autoload)
        if w_res is None:
            return space.w_object.find_const(space, name, autoload=autoload)
        else:
            return w_res

    def find_scoped_const(self, space, name):
        """`Mod::Name`: the module and what it includes, but not Object
        (Ruby 2.5 dropped the top-level fallback)."""
        return self.find_included_const(space, name, autoload=True)

    @jit.unroll_safe
    def find_included_const(self, space, name, autoload=True):
        w_res = self.find_local_const(space, name, autoload=autoload)
        if w_res is None:
            for w_mod in self.included_modules:
                w_res = w_mod.find_local_const(space, name, autoload=autoload)
                if w_res is not None:
                    break
        return w_res

    def included_constants(self, space):
        consts = {}
        for const in self.constants_w:
            consts[const] = None
        for w_mod in self.included_modules:
            for const in w_mod.included_constants(space):
                consts[const] = None
        return consts.keys()

    def lexical_constants(self, space):
        consts = {}
        frame = space.getexecutioncontext().gettoprubyframe()
        scope = frame.lexical_scope

        while scope is not None:
            assert isinstance(scope, W_ModuleObject)
            for const in scope.w_mod.constants_w:
                consts[const] = None
            scope = scope.backscope

        return consts.keys()

    def local_constants(self, space):
        return self.constants_w.keys()

    def inherited_constants(self, space):
        return self.local_constants(space)

    def find_local_const(self, space, name, autoload=True):
        w_res = self._find_const_pure(name, self.version)
        if autoload and isinstance(w_res, W_Autoload):
            self.constants_w[name] = None
            try:
                w_res.load()
            finally:
                w_new_res = self.constants_w.get(name, None)
                if not w_res:
                    self.constants_w[name] = w_res
                w_res = w_new_res
            return w_res
        else:
            return w_res

    @jit.elidable
    def _find_const_pure(self, name, version):
        return self.constants_w.get(name, None)

    @jit.unroll_safe
    def set_class_var(self, space, name, w_obj):
        for module in reversed(self.ancestors()):
            assert isinstance(module, W_ModuleObject)
            w_res = module.class_variables.get(space, name)
            if w_res is not None or module is self:
                module.class_variables.set(space, name, w_obj)
                if module is self:
                    for descendant in self.descendants:
                        descendant.remove_class_var(space, name)

    @jit.unroll_safe
    def find_class_var(self, space, name):
        w_res = self.class_variables.get(space, name)
        if w_res is None:
            ancestors = self.ancestors()
            for idx in xrange(1, len(ancestors)):
                module = ancestors[idx]
                assert isinstance(module, W_ModuleObject)
                w_res = module.class_variables.get(space, name)
                if w_res is not None:
                    break
        return w_res

    @jit.unroll_safe
    def remove_class_var(self, space, name):
        self.class_variables.delete(name)
        for descendant in self.descendants:
            descendant.remove_class_var(space, name)

    def set_instance_var(self, space, name, w_value):
        return self.instance_variables.set(space, name, w_value)

    def find_instance_var(self, space, name):
        return self.instance_variables.get(space, name)

    def instance_variable_names(self, space):
        return [name for name in self.instance_variables]

    def remove_instance_var(self, space, name):
        w_value = self.instance_variables.get(space, name)
        if w_value is not None:
            self.instance_variables.delete(name)
        return w_value

    def copy_instance_vars(self, space, w_other):
        assert isinstance(w_other, W_ModuleObject)
        for key in w_other.instance_variables:
            w_value = w_other.instance_variables.get(space, key)
            self.set_instance_var(space, key, w_value)

    def set_flag(self, space, name):
        self.flags.set(space, name, space.w_true)

    def unset_flag(self, space, name):
        self.flags.set(space, name, space.w_false)

    def get_flag(self, space, name):
        return self.flags.get(space, name) or space.w_false

    def ancestors(self, include_singleton=True, include_self=True):
        if include_self:
            return self.prepended_modules + [self] + self.included_modules
        else:
            return self.prepended_modules + self.included_modules

    @jit.unroll_safe
    def is_ancestor_of(self, w_cls):
        if self is w_cls:
            return True
        for w_mod in w_cls.included_modules:
            if self is w_mod:
                return True
        for w_mod in w_cls.prepended_modules:
            if self is w_mod:
                return True
        if w_cls.superclass is not None:
            return self.is_ancestor_of(w_cls.superclass)
        return False

    def include_module(self, space, w_mod):
        assert isinstance(w_mod, W_ModuleObject)
        if w_mod not in self.ancestors():
            self.included_modules = [w_mod] + self.included_modules
            w_mod.included(space, self)

    def prepend_module(self, space, w_mod):
        assert isinstance(w_mod, W_ModuleObject)
        if w_mod not in self.prepended_modules:
            self.prepended_modules = [w_mod] + self.prepended_modules
            self.mutated()
            w_mod.descendants.append(self)

    def included(self, space, w_mod):
        self.descendants.append(w_mod)
        if space.respond_to(self, "included"):
            space.send(self, "included", [w_mod])

    def extend_object(self, space, w_mod):
        if self not in w_mod.ancestors():
            self.descendants.append(w_mod)
            w_mod.included_modules = [self] + w_mod.included_modules

    def visibility_names(self, space, names_w):
        # Names may come as symbols or strings, or (Ruby 3.0) in an array,
        # as in `private attr_reader :a, :b`.
        names = []
        for w_name in names_w:
            if isinstance(w_name, W_ArrayObject):
                for w_item in space.listview(w_name):
                    names.append(Coerce.symbol(space, w_item))
            else:
                names.append(Coerce.symbol(space, w_name))
        return names

    def set_visibility(self, space, names_w, visibility):
        names = self.visibility_names(space, names_w)
        if names:
            for name in names:
                self.set_method_visibility(space, name, visibility)
        else:
            self.set_default_visibility(space, visibility)

    def visibility_result(self, space, names_w):
        """What private, public and protected return (Ruby 3.0): nil, the
        name, or the array of names."""
        if not names_w:
            return space.w_nil
        if len(names_w) == 1:
            return names_w[0]
        return space.newarray(names_w)

    def set_default_visibility(self, space, visibility):
        frame = space.getexecutioncontext().gettoprubyframe()
        frame.visibility = visibility

    def set_method_visibility(self, space, name, visibility):
        w_method = self.find_method(space, name)
        if w_method is None or isinstance(w_method, UndefMethod):
            w_method = space.w_object.find_method(space, name)

        if w_method is None or isinstance(w_method, UndefMethod):
            cls_name = space.obj_to_s(self)
            raise space.error(space.w_NameError,
                "undefined method '%s' for class '%s'" % (name, cls_name)
            )
        w_method.update_visibility(visibility)

    def method_added(self, space, w_name):
        space.send(self, "method_added", [w_name])

    def method_undefined(self, space, w_name):
        space.send(self, "method_undefined", [w_name])

    def method_removed(self, space, w_name):
        space.send(self, "method_removed", [w_name])

    def set_name_in_scope(self, space, name, w_scope):
        self.name = space.buildname(name, w_scope)
        for name, w_const in self.constants_w.iteritems():
            if isinstance(w_const, W_ModuleObject):
                w_const.set_name_in_scope(space, name, self)

    @classdef.singleton_method("nesting")
    def singleton_method_nesting(self, space):
        frame = space.getexecutioncontext().gettoprubyframe()
        modules_w = []
        scope = frame.lexical_scope
        while scope is not None:
            modules_w.append(scope.w_mod)
            scope = scope.backscope
        return space.newarray(modules_w)

    @classdef.singleton_method("allocate")
    def method_allocate(self, space):
        return W_ModuleObject(space, None, self)

    @classdef.method("initialize")
    def method_initialize(self, space, block):
        if block is not None:
            space.send(self, "module_exec", [self], block)

    @classdef.method("initialize_copy")
    def method_initialize_copy(self, space, w_other):
        # Module#dup and #clone copy the methods, constants and class
        # variables, and include the same modules.
        if not isinstance(w_other, W_ModuleObject):
            raise space.error(space.w_TypeError, "initialize_copy should take same class object")
        for name, w_method in w_other.methods_w.iteritems():
            self.methods_w[name] = w_method
        for name, w_const in w_other.constants_w.iteritems():
            self.constants_w[name] = w_const
        for name in w_other.class_variables:
            w_value = w_other.class_variables.get(space, name)
            if w_value is not None:
                self.class_variables.set(space, name, w_value)
        self.included_modules = w_other.included_modules[:]
        self.prepended_modules = w_other.prepended_modules[:]
        self.mutated()
        return self

    @classdef.method("to_s")
    def method_to_s(self, space):
        name = self.name
        if name is None:
            return space.newstr_fromstr(space.any_to_s(self))
        return space.newstr_fromstr(name)

    @classdef.method("include")
    def method_include(self, space, args_w):
        for w_mod in args_w:
            if type(w_mod) is not W_ModuleObject:
                raise space.error(
                    space.w_TypeError,
                    "wrong argument type %s (expected Module)" % space.obj_to_s(space.getclass(w_mod))
                )

        for w_mod in reversed(args_w):
            space.send(w_mod, "append_features", [self])

        return self

    @classdef.method("include?")
    def method_includep(self, space, w_mod):
        if type(w_mod) is not W_ModuleObject:
            raise space.error(
                space.w_TypeError,
                "wrong argument type %s (expected Module)" % space.obj_to_s(space.getclass(w_mod))
            )
        if w_mod is self:
            return space.w_false
        return space.newbool(w_mod in self.ancestors())

    @classdef.method("append_features")
    def method_append_features(self, space, w_mod):
        if w_mod in self.ancestors():
            raise space.error(space.w_ArgumentError, "cyclic include detected")
        if type(self) is not W_ModuleObject:
            raise space.error(space.w_TypeError, "wrong argument type")
        for module in reversed(self.ancestors()):
            w_mod.include_module(space, module)

    @classdef.method("prepend")
    def method_prepend(self, space, args_w):
        for w_mod in args_w:
            if type(w_mod) is not W_ModuleObject:
                raise space.error(
                    space.w_TypeError,
                    "wrong argument type %s (expected Module)" % space.obj_to_s(space.getclass(w_mod))
                )
        for w_mod in reversed(args_w):
            space.send(w_mod, "prepend_features", [self])
            space.send(w_mod, "prepended", [self])
        return self

    @classdef.method("prepend_features")
    def method_prepend_features(self, space, w_mod):
        if not isinstance(w_mod, W_ModuleObject):
            raise space.error(space.w_TypeError, "wrong argument type")
        if w_mod in self.ancestors():
            raise space.error(space.w_ArgumentError, "cyclic prepend detected")
        for module in reversed(self.ancestors()):
            w_mod.prepend_module(space, module)

    @classdef.method("prepended")
    def method_prepended(self, space, w_mod):
        return space.w_nil

    @classdef.method("define_method", name="symbol")
    @check_frozen()
    def method_define_method(self, space, name, w_method=None, block=None):
        if w_method is not None:
            if space.is_kind_of(w_method, space.w_method):
                w_method = space.send(w_method, "unbind")

            if space.is_kind_of(w_method, space.w_unbound_method):
                self.define_method(space, name, DefineMethodMethod(name, w_method))
                return w_method
            elif space.is_kind_of(w_method, space.w_proc):
                assert isinstance(w_method, W_ProcObject)
                self.define_method(space, name, DefineMethodBlock(name, w_method))
                return w_method.copy(space, is_lambda=True)
            else:
                raise space.error(space.w_TypeError,
                    "wrong argument type %s (expected Proc/Method)" % space.obj_to_s(space.getclass(w_method))
                )
        elif block is not None:
            self.define_method(space, name, DefineMethodBlock(name, block))
            return block.copy(space, is_lambda=True)
        else:
            raise space.error(space.w_ArgumentError, "tried to create Proc object without a block")

    # The attr_* methods return the names of the methods they define
    # (Ruby 3.0), so that `private attr_reader :a` works.

    @classdef.method("attr_accessor")
    def method_attr_accessor(self, space, args_w):
        names_w = []
        for w_arg in args_w:
            varname = Coerce.symbol(space, w_arg)
            self.define_method(space, varname, AttributeReader("@" + varname))
            self.define_method(space, varname + "=", AttributeWriter("@" + varname))
            names_w.append(space.newsymbol(varname))
            names_w.append(space.newsymbol(varname + "="))
        return space.newarray(names_w)

    @classdef.method("attr_reader")
    def method_attr_reader(self, space, args_w):
        names_w = []
        for w_arg in args_w:
            varname = Coerce.symbol(space, w_arg)
            self.define_method(space, varname, AttributeReader("@" + varname))
            names_w.append(space.newsymbol(varname))
        return space.newarray(names_w)

    @classdef.method("attr_writer")
    def method_attr_writer(self, space, args_w):
        names_w = []
        for w_arg in args_w:
            varname = Coerce.symbol(space, w_arg)
            self.define_method(space, varname + "=", AttributeWriter("@" + varname))
            names_w.append(space.newsymbol(varname + "="))
        return space.newarray(names_w)

    @classdef.method("attr")
    def method_attr(self, space, args_w):
        if len(args_w) == 2 and (args_w[1] is space.w_true or args_w[1] is space.w_false):
            [w_name, w_writable] = args_w
            if space.is_true(w_writable):
                return self.method_attr_accessor(space, [w_name])
            else:
                return self.method_attr_reader(space, [w_name])
        else:
            return self.method_attr_reader(space, args_w)

    @classdef.method("ruby2_keywords")
    def method_ruby2_keywords(self, space, args_w):
        """Keyword arguments that the named methods collect in their rest
        parameter stay keyword arguments when splatted into another call,
        the Ruby 2 behaviour delegating methods rely on."""
        for w_arg in args_w:
            name = Coerce.symbol(space, w_arg)
            w_method = self.find_method(space, name)
            if w_method is None or isinstance(w_method, UndefMethod):
                cls_name = space.obj_to_s(self)
                raise space.error(space.w_NameError,
                    "undefined method '%s' for class '%s'" % (name, cls_name)
                )
            if isinstance(w_method, W_UserFunction):
                w_method.bytecode.ruby2_keywords = True
        return space.w_nil

    @classdef.method("module_function")
    def method_module_function(self, space, args_w):
        if not args_w:
            self.set_default_visibility(space, W_FunctionObject.MODULE_FUNCTION)
            return self
        for w_arg in args_w:
            name = Coerce.symbol(space, w_arg)
            w_method = self.find_method(space, name)
            if w_method is None or isinstance(w_method, UndefMethod):
                cls_name = space.obj_to_s(self)
                raise space.error(space.w_NameError,
                    "undefined method '%s' for class '%s'" % (name, cls_name)
                )
            self.attach_method(space, name, w_method)
            self.set_method_visibility(space, name, W_FunctionObject.PRIVATE)
        return self

    @classdef.method("private_class_method")
    def method_private_class_method(self, space, args_w):
        w_cls = self.getsingletonclass(space)
        return space.send(w_cls, "private", args_w)

    @classdef.method("public_class_method")
    def method_public_class_method(self, space, args_w):
        w_cls = self.getsingletonclass(space)
        return space.send(w_cls, "public", args_w)

    @classdef.method("alias_method", new_name="symbol", old_name="symbol")
    @check_frozen()
    def method_alias_method(self, space, new_name, old_name):
        w_method = self.find_method(space, old_name)
        if w_method is None:
            w_method = space.w_object.find_method(space, old_name)
        if w_method is None or isinstance(w_method, UndefMethod):
            cls_name = space.obj_to_s(self)
            raise space.error(space.w_NameError,
                "undefined method '%s' for class '%s'" % (old_name, cls_name)
            )
        self.define_method(space, new_name, w_method)
        return self

    @classdef.method("ancestors")
    def method_ancestors(self, space):
        return space.newarray(self.ancestors(include_singleton=False))

    @classdef.method("included")
    def method_included(self, space, w_mod):
        # TODO: should be private
        pass

    @classdef.method("extended")
    def method_extended(self, space, w_mod):
        # TODO: should be private
        pass

    @classdef.method("extend_object")
    def method_extend_object(self, space, w_obj):
        if type(self) is not W_ModuleObject:
            raise space.error(space.w_TypeError, "wrong argument type")
        self.extend_object(space, space.getsingletonclass(w_obj))

    @classdef.method("name")
    def method_name(self, space):
        if self.name is None:
            return space.w_nil
        return space.newstr_fromstr(self.name)

    @classdef.method("private")
    def method_private(self, space, args_w):
        self.set_visibility(space, args_w, W_FunctionObject.PRIVATE)
        return self.visibility_result(space, args_w)

    @classdef.method("public")
    def method_public(self, space, args_w):
        self.set_visibility(space, args_w, W_FunctionObject.PUBLIC)
        return self.visibility_result(space, args_w)

    @classdef.method("protected")
    def method_protected(self, space, args_w):
        self.set_visibility(space, args_w, W_FunctionObject.PROTECTED)
        return self.visibility_result(space, args_w)

    @classdef.method("private_constant")
    def method_private_constant(self, space, args_w):
        pass

    @classdef.method("constants")
    def method_constants(self, space, w_inherit=None):
        if self is space.w_module and w_inherit is None:
            consts = {}
            for const in self.lexical_constants(space):
                consts[const] = None
            for const in self.inherited_constants(space):
                consts[const] = None
            return space.newarray([space.newsymbol(n) for n in consts])

        if w_inherit is None or space.is_true(w_inherit):
            return space.newarray([space.newsymbol(n) for n in self.included_constants(space)])
        else:
            return space.newarray([space.newsymbol(n) for n in self.constants_w])

    @classdef.method("const_missing", name="symbol")
    def method_const_missing(self, space, name):
        if self is space.w_object:
            raise space.error(space.w_NameError, "uninitialized constant %s" % (name))
        else:
            self_name = space.obj_to_s(self)
            raise space.error(space.w_NameError, "uninitialized constant %s::%s" % (self_name, name))

    @classdef.method("class_eval", string="str", filename="str")
    @classdef.method("module_eval", string="str", filename="str")
    def method_module_eval(self, space, string=None, filename=None, w_lineno=None, block=None):
        if string is not None and block is not None:
            raise space.error(space.w_ArgumentError, "wrong number of arguments")
        if string is not None:
            if filename is None:
                filename = "module_eval"
            if w_lineno is not None:
                lineno = space.int_w(w_lineno)
            else:
                lineno = 1
            return space.execute(string, self, lexical_scope=StaticScope(self, None), filepath=filename, initial_lineno=lineno)
        elif block is None:
            raise space.error(space.w_ArgumentError, "block not supplied")
        else:
            return space.invoke_block(block.copy(space, w_self=self, lexical_scope=StaticScope(self, block.lexical_scope)), [])

    @classdef.method("const_defined?", const="str", inherit="bool")
    def method_const_definedp(self, space, const, inherit=True):
        space._check_const_name(const)
        if inherit:
            return space.newbool(self.find_const(space, const, autoload=False) is not None)
        else:
            return space.newbool(self.find_local_const(space, const, autoload=False) is not None)

    @classdef.method("const_get", const="symbol", inherit="bool")
    def method_const_get(self, space, const, inherit=True):
        space._check_const_name(const)
        if inherit:
            w_res = self.find_const(space, const)
        else:
            w_res = self.find_local_const(space, const)
        if w_res is None:
            return space.send(self, "const_missing", [space.newsymbol(const)])
        return w_res

    @classdef.method("const_set", const="symbol")
    @check_frozen()
    def method_const_set(self, space, const, w_value):
        space.set_const(self, const, w_value)
        return w_value

    @classdef.method("remove_const", name="str")
    def method_remove_const(self, space, name):
        space._check_const_name(name)
        w_res = self.find_local_const(space, name, autoload=False)
        if w_res is None:
            self_name = space.obj_to_s(self)
            raise space.error(space.w_NameError,
                "uninitialized constant %s::%s" % (self_name, name)
            )
        del self.constants_w[name]
        self.mutated()
        return w_res

    @classdef.method("class_variables", inherit="bool")
    def method_class_variables(self, space, inherit=True):
        return space.newarray([space.newsymbol(cvar) for cvar in self.class_variables])

    @classdef.method("singleton_class?")
    def method_singleton_classp(self, space):
        return space.w_false

    @classdef.method("class_variable_defined?", name="symbol")
    def method_class_variable_definedp(self, space, name):
        return space.newbool(self.find_class_var(space, name) is not None)

    @classdef.method("class_variable_get", name="symbol")
    def method_class_variable_get(self, space, name):
        return space.find_class_var(self, name)

    @classdef.method("class_variable_set", name="symbol")
    @check_frozen()
    def method_class_variable_set(self, space, name, w_value):
        self.set_class_var(space, name, w_value)
        return w_value

    @classdef.method("remove_class_variable", name="symbol")
    def method_remove_class_variable(self, space, name):
        w_value = self.class_variables.get(space, name)
        if w_value is not None:
            self.class_variables.delete(name)
            return w_value
        if self.find_class_var(space, name) is not None:
            raise space.error(space.w_NameError,
                "cannot remove %s for %s" % (name, space.obj_to_s(self))
            )
        raise space.error(space.w_NameError,
            "class variable %s not defined for %s" % (name, space.obj_to_s(self))
        )

    def defined_method_visibility(self, space, name, inherit):
        """The visibility of the method `name`, or -1 if it is not defined."""
        if inherit:
            w_method = self.find_method(space, name)
        else:
            w_method = self._find_method_pure(space, name, self.version)
        if w_method is None or isinstance(w_method, UndefMethod):
            return -1
        return w_method.visibility

    @classdef.method("method_defined?", name="str", inherit="bool")
    def method_method_definedp(self, space, name, inherit=True):
        visibility = self.defined_method_visibility(space, name, inherit)
        return space.newbool(visibility == W_FunctionObject.PUBLIC or
                             visibility == W_FunctionObject.PROTECTED)

    @classdef.method("public_method_defined?", name="str", inherit="bool")
    def method_public_method_definedp(self, space, name, inherit=True):
        visibility = self.defined_method_visibility(space, name, inherit)
        return space.newbool(visibility == W_FunctionObject.PUBLIC)

    @classdef.method("private_method_defined?", name="str", inherit="bool")
    def method_private_method_definedp(self, space, name, inherit=True):
        visibility = self.defined_method_visibility(space, name, inherit)
        return space.newbool(visibility == W_FunctionObject.PRIVATE)

    @classdef.method("protected_method_defined?", name="str", inherit="bool")
    def method_protected_method_definedp(self, space, name, inherit=True):
        visibility = self.defined_method_visibility(space, name, inherit)
        return space.newbool(visibility == W_FunctionObject.PROTECTED)

    @classdef.method("===")
    def method_eqeqeq(self, space, w_obj):
        return space.newbool(self.is_ancestor_of(space.getclass(w_obj)))

    @classdef.method("<=")
    def method_lte(self, space, w_other):
        if not isinstance(w_other, W_ModuleObject):
            raise space.error(space.w_TypeError, "compared with non class/module")
        for w_mod in self.ancestors():
            if w_other is w_mod:
                return space.w_true
        for w_mod in w_other.ancestors():
            if self is w_mod:
                return space.w_false
        return space.w_nil

    @classdef.method("<")
    def method_lt(self, space, w_other):
        if self is w_other:
            return space.w_false
        return space.send(self, "<=", [w_other])

    @classdef.method(">=")
    def method_gte(self, space, w_other):
        if not isinstance(w_other, W_ModuleObject):
            raise space.error(space.w_TypeError, "compared with non class/module")
        return space.send(w_other, "<=", [self])

    @classdef.method(">")
    def method_gt(self, space, w_other):
        if not isinstance(w_other, W_ModuleObject):
            raise space.error(space.w_TypeError, "compared with non class/module")
        if self is w_other:
            return space.w_false
        return space.send(w_other, "<=", [self])

    @classdef.method("<=>")
    def method_comparison(self, space, w_other):
        if not isinstance(w_other, W_ModuleObject):
            return space.w_nil

        if self is w_other:
            return space.newint(0)

        other_is_subclass = space.send(self, "<", [w_other])

        if space.is_true(other_is_subclass):
            return space.newint(-1)
        elif other_is_subclass is space.w_nil:
            return space.w_nil
        else:
            return space.newint(1)

    @classdef.method("instance_method", name="symbol")
    def method_instance_method(self, space, name):
        return space.newmethod(name, self)

    @classdef.method("instance_methods", inherit="bool")
    def method_instance_methods(self, space, inherit=True):
        return space.newarray([
            space.newsymbol(sym)
            for sym in self.methods(space, inherit=inherit)
        ])

    @classdef.method("public_instance_methods", inherit="bool")
    def method_public_instance_methods(self, space, inherit=True):
        return space.newarray([
            space.newsymbol(sym)
            for sym in self.methods(space, visibility=W_FunctionObject.PUBLIC, inherit=inherit)
        ])

    @classdef.method("protected_instance_methods", inherit="bool")
    def method_protected_instance_methods(self, space, inherit=True):
        return space.newarray([
            space.newsymbol(sym)
            for sym in self.methods(space, visibility=W_FunctionObject.PROTECTED, inherit=inherit)
        ])

    @classdef.method("private_instance_methods", inherit="bool")
    def method_private_instance_methods(self, space, inherit=True):
        return space.newarray([
            space.newsymbol(sym)
            for sym in self.methods(space, visibility=W_FunctionObject.PRIVATE, inherit=inherit)
        ])

    @classdef.method("undef_method", name="symbol")
    def method_undef_method(self, space, name):
        w_method = self.find_method(space, name)
        if w_method is None or isinstance(w_method, UndefMethod):
            cls_name = space.obj_to_s(self)
            raise space.error(space.w_NameError,
                "undefined method '%s' for class '%s'" % (name, cls_name)
            )
        self.define_method(space, name, UndefMethod(name))
        return self

    @classdef.method("remove_method", name="symbol")
    @check_frozen()
    def method_remove_method(self, space, name):
        w_method = self._find_method_pure(space, name, self.version)
        if w_method is None or isinstance(w_method, UndefMethod):
            cls_name = space.obj_to_s(self)
            raise space.error(space.w_NameError,
                "method `%s' not defined in %s" % (name, cls_name)
            )
        del self.methods_w[name]
        self.mutated()
        self.shadow_hidden_subclasses(name)
        self.method_removed(space, space.newsymbol(name))
        return self

    def method_removed(self, space, w_name):
        space.send(self, "method_removed", [w_name])

    @classdef.method("method_added")
    def method_method_added(self, space, w_name):
        return space.w_nil

    @classdef.method("method_undefined")
    def method_method_undefined(self, space, w_name):
        return space.w_nil

    @classdef.method("method_removed")
    def method_method_removed(self, space, w_name):
        return space.w_nil

    @classdef.method("autoload", name="symbol", path="path")
    def method_autoload(self, space, name, path):
        if len(path) == 0:
            raise space.error(space.w_ArgumentError, "empty file name")
        if not self.find_const(space, name):
            space.set_const(self, name, W_Autoload(space, path))
        return space.w_nil

    @classdef.method("autoload?", name="symbol")
    def method_autoload(self, space, name):
        w_autoload = self.constants_w.get(name, None)
        if isinstance(w_autoload, W_Autoload):
            return space.newstr_fromstr(w_autoload.path)
        else:
            return space.w_nil

    @classdef.method("class_exec")
    @classdef.method("module_exec")
    def method_module_exec(self, space, args_w, block):
        if block is None:
            raise space.error(space.w_LocalJumpError, "no block given")
        return space.invoke_block(
            block.copy(
                space,
                w_self=self,
                lexical_scope=StaticScope(self, None)
            ),
            args_w
        )
