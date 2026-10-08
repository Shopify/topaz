from __future__ import absolute_import

import gc
import os
import sys
import weakref

from rpython.rlib import jit, rpath, types
from rpython.rlib.cache import Cache
from rpython.rlib.objectmodel import compute_identity_hash, specialize, compute_unique_id
from rpython.rlib.signature import signature
from rpython.rlib.rarithmetic import intmask
from rpython.rlib.rbigint import rbigint
from rpython.rtyper.lltypesystem import llmemory, rffi


from topaz import system
from topaz.astcompiler import CompilerContext, SymbolTable, CompilerError
from topaz.celldict import GlobalsDict
from topaz.error import RubyError, print_traceback
from topaz.executioncontext import ExecutionContext, ExecutionContextHolder
from topaz.frame import Frame
from topaz.interpreter import Interpreter
from topaz.prism import parser as prism_parser
from topaz.module import ClassCache, ModuleCache
from topaz.modules.comparable import Comparable
from topaz.modules.enumerable import Enumerable
from topaz.modules.marshal import Marshal
from topaz.modules.math import Math
from topaz.modules.kernel import Kernel
from topaz.modules.fcntl import Fcntl
from topaz.modules.ffi import FFI
from topaz.modules.objectspace import ObjectSpace as ObjectSpaceModule
from topaz.modules.process import Process
from topaz.modules.signal import Signal
from topaz.modules.topaz import Topaz
from topaz.objects.arrayobject import W_ArrayObject
from topaz.objects.bignumobject import W_BignumObject
from topaz.objects.bindingobject import W_BindingObject
from topaz.objects.boolobject import W_TrueObject, W_FalseObject
from topaz.objects.classobject import W_ClassObject
from topaz.objects.codeobject import W_CodeObject
from topaz.objects.dirobject import W_DirObject
from topaz.objects.encodingobject import W_EncodingObject
from topaz.objects.envobject import W_EnvObject
from topaz.objects.exceptionobject import (
    W_ExceptionObject, W_NoMethodError,
    W_ZeroDivisionError, W_SyntaxError, W_LoadError, W_TypeError,
    W_ArgumentError, W_RuntimeError, W_StandardError, W_SystemExit,
    W_SystemCallError, W_NameError, W_IndexError, W_KeyError, W_StopIteration,
    W_NotImplementedError, W_RangeError, W_LocalJumpError, W_IOError,
    W_RegexpError, W_ThreadError, W_FiberError, W_EOFError, W_FloatDomainError,
    W_SystemStackError)
from topaz.objects.fiberobject import W_FiberObject
from topaz.objects.fileobject import W_FileObject
from topaz.objects.floatobject import W_FloatObject
from topaz.objects.functionobject import W_UserFunction
from topaz.objects.hashobject import W_HashObject, W_HashIterator
from topaz.objects.integerdispatch import W_IntegerDispatchFunction
from topaz.objects.integerobject import W_IntegerObject
from topaz.objects.intobject import W_FixnumObject
from topaz.objects.ioobject import W_IOObject
from topaz.objects.methodobject import W_MethodObject, W_UnboundMethodObject
from topaz.objects.moduleobject import UndefMethod, W_ModuleObject
from topaz.objects.mutexobject import W_MonitorObject
from topaz.objects.nilobject import W_NilObject
from topaz.objects.numericobject import W_NumericObject
from topaz.objects.objectobject import W_Object, W_BaseObject, W_Root
from topaz.objects.procobject import W_ProcObject
from topaz.objects.randomobject import W_RandomObject
from topaz.objects.rangeobject import W_RangeObject
from topaz.objects.regexpobject import W_RegexpObject, W_MatchDataObject
from topaz.objects.stringobject import W_StringObject
from topaz.objects.symbolobject import W_SymbolObject
from topaz.objects.threadobject import W_ThreadObject
from topaz.objects.timeobject import W_TimeObject
from topaz.utils.ll_file import isdir


class EncodingCache(object):
    """Encoding objects looked up once lib-topaz/encoding.rb has defined
    them. The space itself is a frozen prebuilt constant, so the cache
    lives on a separate object."""
    def __init__(self):
        self.w_binary = None


class SpaceCache(Cache):
    def __init__(self, space):
        Cache.__init__(self)
        self.space = space

    def _build(self, obj):
        return obj(self.space)



class LibPaths(object):
    def __init__(self, ext_lib_path):
        self.ext_lib_path = ext_lib_path

class InterpProfile(object):
    """For Topaz.interp_profile (the space itself is a prebuilt constant)."""

    def __init__(self):
        self.enabled = False
        self.codes_w = []


class ObjectSpace(object):
    def __init__(self, config):
        self.config = config

        self.cache = SpaceCache(self)
        self.symbol_cache = {}
        self._executioncontexts = ExecutionContextHolder()
        self.globals = GlobalsDict()
        self.bootstrap = True
        self.exit_handlers_w = []
        # Topaz.interp_profile: code objects run by the interpreter (outside
        # compiled code), counted when TOPAZ_INTERP_PROFILE is set.
        self.interp_profile = InterpProfile()

        self.w_true = W_TrueObject(self)
        self.w_false = W_FalseObject(self)
        self.w_nil = W_NilObject(self)

        # Force the setup of a few key classes, we create a fake "Class" class
        # for the initial bootstrap.
        self.w_class = self.newclass("FakeClass", None)
        cls_reference = weakref.ref(self.w_class)
        self.w_basicobject = self.getclassfor(W_BaseObject)
        self.w_object = self.getclassfor(W_Object)
        self.w_class = self.getclassfor(W_ClassObject)
        # We replace the one reference to our FakeClass with the real class.
        self.w_basicobject.klass.superclass = self.w_class
        self.w_class.add_descendant(self.w_basicobject.klass)

        gc.collect()
        assert cls_reference() is None

        self.w_symbol = self.getclassfor(W_SymbolObject)
        self.w_array = self.getclassfor(W_ArrayObject)
        self.w_proc = self.getclassfor(W_ProcObject)
        self.w_binding = self.getclassfor(W_BindingObject)
        self.w_numeric = self.getclassfor(W_NumericObject)
        self.w_fixnum = self.getclassfor(W_FixnumObject)
        self.w_float = self.getclassfor(W_FloatObject)
        self.w_bignum = self.getclassfor(W_BignumObject)
        self.w_integer = self.getclassfor(W_IntegerObject)
        # Ruby >= 2.4 has only Integer; the fixnum/bignum classes are hidden.
        self.w_fixnum.is_hidden = True
        self.w_bignum.is_hidden = True
        self.w_module = self.getclassfor(W_ModuleObject)
        self.w_string = self.getclassfor(W_StringObject)
        self.w_regexp = self.getclassfor(W_RegexpObject)
        self.w_hash = self.getclassfor(W_HashObject)
        self.w_method = self.getclassfor(W_MethodObject)
        self.w_unbound_method = self.getclassfor(W_UnboundMethodObject)
        self.w_io = self.getclassfor(W_IOObject)
        self.w_NoMethodError = self.getclassfor(W_NoMethodError)
        # Encoding::ASCII_8BIT, looked up on first use (lib-topaz/encoding.rb
        # defines it).
        self.encoding_cache = EncodingCache()
        self.w_ArgumentError = self.getclassfor(W_ArgumentError)
        self.w_LocalJumpError = self.getclassfor(W_LocalJumpError)
        self.w_NameError = self.getclassfor(W_NameError)
        self.w_NotImplementedError = self.getclassfor(W_NotImplementedError)
        self.w_IndexError = self.getclassfor(W_IndexError)
        self.w_KeyError = self.getclassfor(W_KeyError)
        self.w_IOError = self.getclassfor(W_IOError)
        self.w_EOFError = self.getclassfor(W_EOFError)
        self.w_FiberError = self.getclassfor(W_FiberError)
        self.w_LoadError = self.getclassfor(W_LoadError)
        self.w_RangeError = self.getclassfor(W_RangeError)
        self.w_FloatDomainError = self.getclassfor(W_FloatDomainError)
        self.w_RegexpError = self.getclassfor(W_RegexpError)
        self.w_RuntimeError = self.getclassfor(W_RuntimeError)
        self.w_StandardError = self.getclassfor(W_StandardError)
        self.w_StopIteration = self.getclassfor(W_StopIteration)
        self.w_SyntaxError = self.getclassfor(W_SyntaxError)
        self.w_SystemCallError = self.getclassfor(W_SystemCallError)
        self.w_SystemExit = self.getclassfor(W_SystemExit)
        self.w_SystemStackError = self.getclassfor(W_SystemStackError)
        self.w_TypeError = self.getclassfor(W_TypeError)
        self.w_ZeroDivisionError = self.getclassfor(W_ZeroDivisionError)
        self.w_kernel = self.getmoduleobject(Kernel.moduledef)

        self.w_topaz = self.getmoduleobject(Topaz.moduledef)

        for w_cls in [
            self.w_basicobject, self.w_object, self.w_array, self.w_proc,
            self.w_numeric, self.w_float,
            self.w_string, self.w_symbol, self.w_class, self.w_module,
            self.w_hash, self.w_regexp, self.w_method, self.w_unbound_method,
            self.w_io, self.w_binding,

            self.w_NoMethodError, self.w_ArgumentError, self.w_TypeError,
            self.w_ZeroDivisionError, self.w_SystemExit, self.w_RangeError,
            self.w_RegexpError, self.w_RuntimeError, self.w_SystemCallError,
            self.w_LoadError, self.w_StopIteration, self.w_SyntaxError,
            self.w_NameError, self.w_StandardError, self.w_LocalJumpError,
            self.w_IndexError, self.w_IOError, self.w_NotImplementedError,
            self.w_EOFError, self.w_FloatDomainError, self.w_FiberError,
            self.w_SystemStackError, self.w_KeyError,

            self.w_kernel, self.w_topaz,

            self.getclassfor(W_NilObject),
            self.getclassfor(W_TrueObject),
            self.getclassfor(W_FalseObject),
            self.getclassfor(W_RangeObject),
            self.getclassfor(W_FileObject),
            self.getclassfor(W_DirObject),
            self.getclassfor(W_EncodingObject),
            self.getclassfor(W_IntegerObject),
            self.getclassfor(W_RandomObject),
            self.getclassfor(W_ThreadObject),
            self.getclassfor(W_MonitorObject),
            self.getclassfor(W_TimeObject),
            self.getclassfor(W_MethodObject),
            self.getclassfor(W_UnboundMethodObject),
            self.getclassfor(W_FiberObject),
            self.getclassfor(W_MatchDataObject),

            self.getclassfor(W_ExceptionObject),
            self.getclassfor(W_ThreadError),

            self.getmoduleobject(Comparable.moduledef),
            self.getmoduleobject(Enumerable.moduledef),
            self.getmoduleobject(Marshal.moduledef),
            self.getmoduleobject(Math.moduledef),
            self.getmoduleobject(Fcntl.moduledef),
            self.getmoduleobject(FFI.moduledef),
            self.getmoduleobject(Process.moduledef),
            self.getmoduleobject(Signal.moduledef),
            self.getmoduleobject(ObjectSpaceModule.moduledef),
        ]:
            self.set_const(
                self.w_object,
                self.str_w(self.send(w_cls, "name")),
                w_cls
            )

        for w_cls in [
            self.getclassfor(W_EnvObject), self.getclassfor(W_HashIterator),
        ]:
            self.set_const(
                self.w_topaz,
                self.str_w(self.send(w_cls, "name")),
                w_cls
            )
        # The Fixnum and Bignum constants are gone since Ruby 3.2; the kernel
        # still needs to name the machine-word class to ask for C-long sized
        # arguments.
        self.set_const(self.w_topaz, "Fixnum", self.w_fixnum)
        self.set_const(self.w_topaz, "Bignum", self.w_bignum)

        self.set_const(self.w_basicobject, "BasicObject", self.w_basicobject)

        # This is bootstrap. We have to delay sending until true, false and nil
        # are defined
        self.send(self.w_object, "include", [self.w_kernel])
        self.bootstrap = False

        self.w_load_path = self.newarray([])
        self.globals.define_virtual(
            "$LOAD_PATH", lambda space: space.w_load_path)
        self.globals.define_virtual("$:", lambda space: space.w_load_path)

        self.globals.define_virtual(
            "$$", lambda space: space.send(space.getmoduleobject(Process.moduledef), "pid"))

        self.w_loaded_features = self.newarray([])
        self.globals.define_virtual(
            "$LOADED_FEATURES", lambda space: space.w_loaded_features)
        self.globals.define_virtual(
            '$"', lambda space: space.w_loaded_features)

        self.w_main_thread = W_ThreadObject(self)

        self.w_load_path = self.newarray([])
        self.base_lib_path = os.path.abspath(os.path.join(os.path.join(
            os.path.dirname(__file__), os.path.pardir), "lib-ruby"))
        # Ruby replacements for C extensions (see Kernel.find_feature). The
        # space is frozen when translated, so the path lives in a holder.
        self.lib_paths = LibPaths(os.path.join(self.base_lib_path, "ext"))

    def _freeze_(self):
        self._executioncontexts.clear()
        return True

    def find_executable(self, executable):
        if os.sep in executable or (system.IS_WINDOWS and ":" in executable):
            return executable
        path = os.environ.get("PATH")
        if path:
            for dir in path.split(os.pathsep):
                f = os.path.join(dir, executable)
                if os.path.isfile(f):
                    executable = f
                    break
        return rpath.rabspath(executable)

    def setup(self, executable):
        """
        Performs runtime setup.
        """
        path = rpath.rabspath(self.find_executable(executable))
        # Fallback to a path relative to the compiled location.
        lib_path = self.base_lib_path
        kernel_path = os.path.join(
            os.path.join(lib_path, os.path.pardir), "lib-topaz")
        while True:
            par_path = rpath.rabspath(os.path.join(path, os.path.pardir))
            if par_path == path:
                break
            path = par_path
            if isdir(os.path.join(path, "lib-ruby")):
                lib_path = os.path.join(path, "lib-ruby")
                kernel_path = os.path.join(path, "lib-topaz")
                break
        self.send(self.w_load_path, "unshift", [self.newstr_fromstr(lib_path)])
        self.lib_paths.ext_lib_path = os.path.join(lib_path, "ext")
        self.load_kernel(kernel_path)
        self.hide_integer_subclasses()

        self.set_const(
            self.w_object,
            "RUBY_ENGINE", self.newstr_fromstr(system.RUBY_ENGINE))
        self.set_const(
            self.w_object,
            "RUBY_VERSION", self.newstr_fromstr(system.RUBY_VERSION))
        self.set_const(
            self.w_object,
            "RUBY_PATCHLEVEL", self.newint(system.RUBY_PATCHLEVEL))
        self.set_const(
            self.w_object,
            "RUBY_PLATFORM", self.newstr_fromstr(system.RUBY_PLATFORM))
        self.set_const(
            self.w_object,
            "RUBY_DESCRIPTION", self.newstr_fromstr(system.RUBY_DESCRIPTION))
        self.set_const(
            self.w_object,
            "RUBY_REVISION", self.newstr_fromstr(system.RUBY_REVISION))
        self.set_const(
            self.w_object,
            "RUBY_RELEASE_DATE", self.newstr_fromstr(system.RUBY_RELEASE_DATE))
        self.set_const(
            self.w_object,
            "RUBY_COPYRIGHT", self.newstr_fromstr(system.RUBY_COPYRIGHT))
        self.set_const(
            self.w_object,
            "RUBY_ENGINE_VERSION",
            self.newstr_fromstr(system.RUBY_ENGINE_VERSION))

    def load_kernel(self, kernel_path):
        self.send(
            self.w_kernel,
            "load",
            [self.newstr_fromstr(os.path.join(kernel_path, "bootstrap.rb"))]
        )

    def hide_integer_subclasses(self):
        """Make Integer own the methods of its hidden fixnum and bignum
        classes; see topaz/objects/integerdispatch.py."""
        w_integer = self.w_integer
        names = {}
        for w_sub in [self.w_fixnum, self.w_bignum]:
            for name in w_sub.methods_w:
                names[name] = None
        for name in names:
            if name in w_integer.methods_w:
                continue
            w_fixnum_method = self.w_fixnum.methods_w.get(name, None)
            if isinstance(w_fixnum_method, UndefMethod):
                w_fixnum_method = None
            w_bignum_method = self.w_bignum.methods_w.get(name, None)
            if isinstance(w_bignum_method, UndefMethod):
                w_bignum_method = None
            if w_fixnum_method is None and w_bignum_method is None:
                continue
            if w_fixnum_method is not None:
                visibility = w_fixnum_method.visibility
            else:
                visibility = w_bignum_method.visibility
            w_integer.methods_w[name] = W_IntegerDispatchFunction(
                name, w_integer, w_fixnum_method, w_bignum_method,
                visibility=visibility
            )
        w_integer.mutated()
        w_integer.hidden_subclasses = [self.w_fixnum, self.w_bignum]

    @specialize.memo()
    def fromcache(self, key):
        return self.cache.getorbuild(key)

    # Methods for dealing with source code.

    def parse(self, source, initial_lineno=1, symtable=None):
        if symtable is None:
            symtable = SymbolTable()
        try:
            return prism_parser.parse(source, initial_lineno, symtable)
        except prism_parser.ParseError as e:
            raise self.error(
                self.w_SyntaxError, "line %d (%s)" % (e.lineno, e.msg))

    def compile(self, source, filepath, initial_lineno=1, symtable=None):
        if symtable is None:
            symtable = SymbolTable()
        astnode = self.parse(
            source, initial_lineno=initial_lineno, symtable=symtable)
        ctx = CompilerContext(self, "<main>", symtable, filepath)
        with ctx.set_lineno(initial_lineno):
            try:
                astnode.compile(ctx)
            except CompilerError as e:
                raise self.error(self.w_SyntaxError, "%s" % e.msg)
        return ctx.create_bytecode(initial_lineno, [], [], None, None)

    def execute(self, source, w_self=None, lexical_scope=None, filepath="-e",
                initial_lineno=1):
        bc = self.compile(source, filepath, initial_lineno=initial_lineno)
        frame = self.create_frame(
            bc, w_self=w_self, lexical_scope=lexical_scope)
        with self.getexecutioncontext().visit_frame(frame):
            return self.execute_frame(frame, bc)

    @jit.loop_invariant
    def getexecutioncontext(self):
        ec = self._executioncontexts.get()
        if ec is None:
            ec = ExecutionContext()
            self._executioncontexts.set(ec)
        return ec

    def create_frame(self, bc, w_self=None, lexical_scope=None, block=None,
                     parent_interp=None, top_parent_interp=None,
                     regexp_match_cell=None):

        if w_self is None:
            w_self = self.w_top_self
        return Frame(
            jit.promote(bc), w_self, lexical_scope, block, parent_interp,
            top_parent_interp, regexp_match_cell
        )

    def execute_frame(self, frame, bc):
        return Interpreter().run(self, frame, bc)

    # Methods for allocating new objects.

    @signature(types.any(), types.bool(), returns=types.instance(W_Root))
    def newbool(self, boolvalue):
        if boolvalue:
            return self.w_true
        else:
            return self.w_false

    @signature(types.any(), types.int(),
               returns=types.instance(W_FixnumObject))
    def newint(self, intvalue):
        return W_FixnumObject(self, intvalue)

    def newbigint_fromint(self, intvalue):
        return W_BignumObject.newbigint_fromint(self, intvalue)

    def newbigint_fromfloat(self, floatvalue):
        return W_BignumObject.newbigint_fromfloat(self, floatvalue)

    def newbigint_fromrbigint(self, bigint):
        # Integers that fit in a machine word are Fixnums, whatever computed
        # them.
        try:
            return self.newint(bigint.toint())
        except OverflowError:
            return W_BignumObject.newbigint_fromrbigint(self, bigint)

    @specialize.argtype(1)
    def newint_or_bigint(self, someinteger):
        if -sys.maxint <= someinteger <= sys.maxint:
            # The smallest int -sys.maxint - 1 has to be a Bignum,
            # because parsing gives a Bignum in that case
            return self.newint(intmask(someinteger))
        else:
            return self.newbigint_fromrbigint(
                rbigint.fromrarith_int(someinteger))

    @specialize.argtype(1)
    def newint_or_bigint_fromunsigned(self, someunsigned):
        # XXX somehow combine with above
        if 0 <= someunsigned <= sys.maxint:
            return self.newint(intmask(someunsigned))
        else:
            return self.newbigint_fromrbigint(
                rbigint.fromrarith_int(someunsigned))

    def newfloat(self, floatvalue):
        return W_FloatObject(self, floatvalue)

    @jit.elidable
    def newsymbol(self, symbol):
        try:
            w_sym = self.symbol_cache[symbol]
        except KeyError:
            w_sym = self.symbol_cache[symbol] = W_SymbolObject(self, symbol)
        return w_sym

    def newstr_fromchars(self, chars):
        return W_StringObject.newstr_fromchars(self, chars)

    def newstr_fromstr(self, strvalue):
        assert strvalue is not None
        return W_StringObject.newstr_fromstr(self, strvalue)

    def newstr_fromstrs(self, strs_w):
        return W_StringObject.newstr_fromstrs(self, strs_w)

    def newarray(self, items_w):
        return W_ArrayObject(self, items_w)

    def newhash(self):
        return W_HashObject(self)

    def newrange(self, w_start, w_end, exclusive):
        return W_RangeObject(self, w_start, w_end, exclusive)

    def newregexp(self, regexp, flags):
        return W_RegexpObject(self, regexp, flags)

    def newmodule(self, name, w_scope=None):
        complete_name = self.buildname(name, w_scope)
        return W_ModuleObject(self, complete_name)

    def newclass(self, name, superclass, is_singleton=False, w_scope=None,
                 attached=None):
        complete_name = self.buildname(name, w_scope)
        return W_ClassObject(
            self, complete_name, superclass,
            is_singleton=is_singleton, attached=attached)

    def newfunction(self, w_name, w_code, lexical_scope, visibility):
        name = self.symbol_w(w_name)
        assert isinstance(w_code, W_CodeObject)
        return W_UserFunction(name, w_code, lexical_scope, visibility)

    def newmethod(self, name, w_cls):
        w_function = w_cls.find_method(self, name)
        if w_function is None:
            raise self.error(
                self.w_NameError,
                "undefined method '%s' for class '%s'" % (
                    name, self.obj_to_s(w_cls)))
        else:
            # The owner is the ancestor that defines the method.
            w_owner = w_cls
            for w_mod in w_cls.ancestors():
                assert isinstance(w_mod, W_ModuleObject)
                if w_mod.find_local_method(self, name) is not None:
                    w_owner = w_mod
                    break
            return W_UnboundMethodObject(self, w_owner, w_function)

    def newproc(self, bytecode, w_self, lexical_scope, cells, block,
                parent_interp, top_parent_interp, regexp_match_cell,
                is_lambda=False):
        return W_ProcObject(
            self, bytecode, w_self, lexical_scope, cells, block, parent_interp,
            top_parent_interp, regexp_match_cell, is_lambda=False
        )

    @jit.unroll_safe
    def newbinding_fromframe(self, frame):
        names = frame.bytecode.cellvars + frame.bytecode.freevars
        cells = [None] * len(names)
        for i in xrange(len(names)):
            cells[i] = frame.get_cell(i).upgrade_to_closure(self, frame, i)
        return W_BindingObject(
            self, names, cells, frame.w_self, frame.lexical_scope)

    @jit.unroll_safe
    def newbinding_fromblock(self, block):
        names = block.bytecode.cellvars + block.bytecode.freevars
        cells = block.cells[:]
        return W_BindingObject(
            self, names, cells, block.w_self, block.lexical_scope)

    def buildname(self, name, w_scope):
        complete_name = name
        if w_scope is not None:
            assert isinstance(w_scope, W_ModuleObject)
            if w_scope is not self.w_object:
                complete_name = "%s::%s" % (self.obj_to_s(w_scope), name)
        return complete_name

    def int_w(self, w_obj):
        return w_obj.int_w(self)

    def bigint_w(self, w_obj):
        return w_obj.bigint_w(self)

    def float_w(self, w_obj):
        return w_obj.float_w(self)

    def symbol_w(self, w_obj):
        return w_obj.symbol_w(self)

    def str_w(self, w_obj):
        """Unpacks a string object as an rstr."""
        return w_obj.str_w(self)

    def str0_w(self, w_obj):
        string = w_obj.str_w(self)
        if "\x00" in string:
            raise self.error(self.w_ArgumentError, "string contains null byte")
        else:
            return string

    def listview(self, w_obj):
        return w_obj.listview(self)

    # Methods for implementing the language semantics.

    def is_true(self, w_obj):
        return w_obj.is_true(self)

    def getclass(self, w_receiver):
        return w_receiver.getclass(self)

    def getsingletonclass(self, w_receiver):
        return w_receiver.getsingletonclass(self)

    def getscope(self, w_receiver):
        if isinstance(w_receiver, W_ModuleObject):
            return w_receiver
        else:
            return self.getclass(w_receiver)

    @jit.unroll_safe
    def getnonsingletonclass(self, w_receiver):
        cls = self.getclass(w_receiver)
        while cls.is_singleton or cls.is_hidden:
            cls = cls.superclass
        return cls

    def getclassfor(self, cls):
        return self.getclassobject(cls.classdef)

    def getclassobject(self, classdef):
        return self.fromcache(ClassCache).getorbuild(classdef)

    def getmoduleobject(self, moduledef):
        return self.fromcache(ModuleCache).getorbuild(moduledef)

    def find_const(self, w_module, name):
        w_res = w_module.find_const(self, name, autoload=True)
        if w_res is None:
            w_res = self.send(
                w_module, "const_missing", [self.newsymbol(name)])
        return w_res

    @jit.elidable
    def _valid_const_name(self, name):
        if not name[0].isupper():
            return False
        for i in range(1, len(name)):
            ch = name[i]
            if not (ch.isalnum() or ch == "_" or ord(ch) > 127):
                return False
        return True

    def _check_const_name(self, name):
        if not self._valid_const_name(name):
            raise self.error(self.w_NameError, "wrong constant name %s" % name)

    def set_const(self, module, name, w_value):
        self._check_const_name(name)
        module.set_const(self, name, w_value)

    @jit.unroll_safe
    def _find_lexical_const(self, lexical_scope, name, autoload=True):
        w_res = None
        scope = lexical_scope
        # perform lexical search but skip Object
        while scope is not None:
            w_mod = scope.w_mod
            if w_mod is self.w_top_self:
                break
            w_res = w_mod.find_local_const(self, name, autoload=autoload)
            if w_res is not None:
                return w_res
            scope = scope.backscope

        object_seen = False
        fallback_scope = self.w_object

        if lexical_scope is not None:
            w_mod = lexical_scope.w_mod
            while w_mod is not None:
                object_seen = object_seen or w_mod is self.w_object
                # BasicObject was our starting point, do not use Object
                # as fallback
                if w_mod is self.w_basicobject and not object_seen:
                    fallback_scope = None
                w_res = w_mod.find_const(self, name, autoload=autoload)
                if w_res is not None:
                    return w_res
                if isinstance(w_mod, W_ClassObject):
                    w_mod = w_mod.superclass
                else:
                    break

        if fallback_scope is not None:
            w_res = fallback_scope.find_const(self, name, autoload=autoload)
        return w_res

    @jit.unroll_safe
    def find_lexical_const(self, lexical_scope, name):
        w_res = self._find_lexical_const(lexical_scope, name)
        if w_res is None:
            if lexical_scope is not None:
                w_mod = lexical_scope.w_mod
            else:
                w_mod = self.w_object
            w_res = self.send(w_mod, "const_missing", [self.newsymbol(name)])
        return w_res

    def find_instance_var(self, w_obj, name):
        w_res = w_obj.find_instance_var(self, name)
        return w_res if w_res is not None else self.w_nil

    def set_instance_var(self, w_obj, name, w_value):
        w_obj.set_instance_var(self, name, w_value)

    def find_class_var(self, w_module, name):
        w_res = w_module.find_class_var(self, name)
        if w_res is None:
            module_name = self.obj_to_s(w_module)
            raise self.error(
                self.w_NameError,
                "uninitialized class variable %s in %s" % (name, module_name))
        return w_res

    def set_class_var(self, w_module, name, w_value):
        w_module.set_class_var(self, name, w_value)

    def send(self, w_receiver, name, args_w=None, block=None):
        if args_w is None:
            args_w = []

        w_cls = self.getclass(w_receiver)
        raw_method = w_cls.find_method(self, name)
        return self._send_raw(
            name, raw_method, w_receiver, w_cls, args_w, block)

    @jit.unroll_safe
    def send_valuestack(self, name, nargs, caller):
        finaldepth = jit.promote(caller.stackpos) - nargs - 1
        assert finaldepth >= 0
        frame = None
        args_w = None
        w_receiver = caller.peek(nargs)
        try:
            w_cls = self.getclass(w_receiver)
            raw_method = w_cls.find_method(self, name)
        except:
            caller.dropvaluesuntil(finaldepth)
            raise
        if isinstance(raw_method, W_UserFunction):
            bc = raw_method.bytecode
            if bc.fast_arity == nargs:
                # Even an empty keyword hash changes argument counting.
                w_last = caller.peek() if nargs else None
                if not (isinstance(w_last, W_HashObject) and w_last.is_keywords):
                    try:
                        frame = self.create_frame(
                            bc, w_self=w_receiver,
                            lexical_scope=raw_method.lexical_scope)
                    except:
                        caller.dropvaluesuntil(finaldepth)
                        raise
                    frame.w_owner = raw_method.w_owner
                    for i in xrange(nargs):
                        pos = bc.arg_pos[i]
                        assert pos >= 0
                        frame.localsstack_w[pos] = caller.peek(nargs - 1 - i)
        # Keep stack accesses outside catch-all handlers: catching IndexError
        # makes RPython emit bounds checks incompatible with virtualizable arrays.
        if frame is None:
            args_w = caller.popitemsreverse(nargs)
        caller.dropvaluesuntil(finaldepth)
        if frame is not None:
            with self.getexecutioncontext().visit_frame(frame):
                return self.execute_frame(frame, frame.bytecode)
        return self._send_raw(name, raw_method, w_receiver, w_cls, args_w, None)

    def send_super(self, w_cls, w_receiver, name, args_w, block=None):
        raw_method = w_cls.find_method_super(self, name)
        return self._send_raw(
            name, raw_method, w_receiver, w_cls, args_w, block)

    def frozen_error(self, w_obj):
        """FrozenError (a RuntimeError) for modifying w_obj."""
        w_cls = self.w_object.find_const(self, "FrozenError", autoload=False)
        if w_cls is None:
            w_cls = self.w_RuntimeError
        name = self.getnonsingletonclass(w_obj).name
        w_inspect = self.send(w_obj, "inspect")
        error = self.error(w_cls, "can't modify frozen %s: %s" % (
            name, self.str_w(w_inspect)))
        error.w_value.set_instance_var(self, "@receiver", w_obj)
        return error

    def send_super_from(self, w_owner, w_receiver, name, args_w, block=None,
                        occurrence=0):
        """`super` in a method defined in w_owner: the next method in the
        receiver's ancestors."""
        w_cls = self.getclass(w_receiver)
        raw_method, next_occurrence = w_cls.find_method_after_with_occurrence(
            self, w_owner, name, occurrence)
        if raw_method is not None:
            return raw_method.call_with_super(
                self, w_receiver, args_w, block, next_occurrence)
        return self._send_raw(
            name, raw_method, w_receiver, w_cls, args_w, block)

    def _send_raw(self, name, raw_method, w_receiver, w_cls, args_w, block):
        if raw_method is None:
            method_missing = w_cls.find_method(self, "method_missing")
            if method_missing is None:
                raise self.undefined_method_error(name, w_receiver)
            else:
                args_w = [self.newsymbol(name)] + args_w
                return method_missing.call(self, w_receiver, args_w, block)
        return raw_method.call(self, w_receiver, args_w, block)

    def encoding_binary(self):
        cache = self.encoding_cache
        w_enc = cache.w_binary
        if w_enc is None:
            w_encoding = self.find_const(self.w_object, "Encoding")
            w_enc = self.find_const(w_encoding, "ASCII_8BIT")
            cache.w_binary = w_enc
        return w_enc

    def respond_to(self, w_receiver, name):
        w_cls = self.getclass(w_receiver)
        raw_method = w_cls.find_method(self, name)
        return raw_method is not None

    def is_kind_of(self, w_obj, w_cls):
        return w_obj.is_kind_of(self, w_cls)

    @jit.unroll_safe
    def invoke_block(self, block, args_w, block_arg=None):
        bc = block.bytecode
        if block.is_lambda:
            # A return in a lambda's body, or in a block the body creates,
            # returns from the lambda: it targets the interpreter running
            # the lambda's frame, which catches it. A return raised by a
            # block that was merely passed through the lambda (a
            # define_method wrapper forwarding &b, say) keeps its own
            # target and propagates past it.
            interp = Interpreter()
            top_parent_interp = interp
        else:
            interp = None
            top_parent_interp = block.top_parent_interp
        frame = self.create_frame(
            bc, w_self=block.w_self, lexical_scope=block.lexical_scope,
            block=block.block, parent_interp=block.parent_interp,
            top_parent_interp=top_parent_interp,
            regexp_match_cell=block.regexp_match_cell,
        )
        frame.w_owner = block.w_owner
        frame.super_occurrence = block.super_occurrence
        frame.super_name = block.super_name
        if block.is_lambda:
            frame.handle_args(self, bc, args_w, block_arg)
        else:
            if (len(bc.arg_pos) != 0 or bc.splat_arg_pos != -1 or
                    bc.block_arg_pos != -1):
                frame.handle_block_args(self, bc, args_w, block_arg)
        assert len(block.cells) == len(bc.freevars)
        for i in xrange(len(bc.freevars)):
            frame.set_cell(len(bc.cellvars) + i, block.cells[i])

        with self.getexecutioncontext().visit_frame(frame):
            if interp is not None:
                return interp.run(self, frame, bc)
            return self.execute_frame(frame, bc)

    def invoke_function(self, w_function, w_receiver, args_w, block):
        return self._send_raw(
            w_function.name, w_function, w_receiver, self.getclass(w_receiver),
            args_w, block)

    def error(self, w_type, msg="", optargs=None):
        if not optargs:
            optargs = []
        args_w = [self.newstr_fromstr(msg)] + optargs
        w_exc = self.send(w_type, "new", args_w)
        assert isinstance(w_exc, W_ExceptionObject)
        return RubyError(w_exc)

    # The hash and equality functions of a Hash's dictionary. As in MRI
    # (rb_any_hash / rb_any_cmp), a Fixnum, a Symbol or a String whose
    # class is exactly String is hashed and compared directly, without
    # dispatching to `hash` / `eql?`: a redefinition of those methods on
    # the core classes is not seen by Hash lookups. The direct values
    # equal what the builtin methods return, so a user object whose eql?
    # and hash mimic a string's still works as a key.
    def hash_w(self, w_obj):
        if isinstance(w_obj, W_FixnumObject):
            return w_obj.intvalue
        if isinstance(w_obj, W_StringObject) and w_obj.klass is self.w_string:
            return w_obj.strategy.hash(w_obj.str_storage)
        if isinstance(w_obj, W_SymbolObject):
            return compute_identity_hash(w_obj)
        return self.int_w(self.send(w_obj, "hash"))

    def eq_w(self, w_obj1, w_obj2):
        if w_obj1 is w_obj2:
            return True
        if isinstance(w_obj1, W_FixnumObject):
            if isinstance(w_obj2, W_FixnumObject):
                return w_obj1.intvalue == w_obj2.intvalue
        elif isinstance(w_obj1, W_StringObject):
            if (isinstance(w_obj2, W_StringObject) and
                    w_obj1.klass is self.w_string and
                    w_obj2.klass is self.w_string):
                return w_obj1.str_w(self) == w_obj2.str_w(self)
        elif isinstance(w_obj1, W_SymbolObject):
            if isinstance(w_obj2, W_SymbolObject):
                return False
        return self.is_true(self.send(w_obj2, "eql?", [w_obj1]))

    def register_exit_handler(self, w_proc):
        self.exit_handlers_w.append(w_proc)

    def run_exit_handlers(self):
        status = -1
        while self.exit_handlers_w:
            w_proc = self.exit_handlers_w.pop()
            try:
                self.send(w_proc, "call")
            except RubyError as e:
                w_exc = e.w_value
                if isinstance(w_exc, W_SystemExit):
                    status = w_exc.status
                else:
                    print_traceback(self, e.w_value)
        return status

    def subscript_access(self, length, w_idx, w_count):
        inclusive = False
        as_range = False
        end = 0
        nil = False

        if isinstance(w_idx, W_RangeObject) and not w_count:
            # A nil begin or end (Ruby 2.6/2.7) stands for the start or the
            # end of the sequence.
            if w_idx.w_start is self.w_nil:
                start = 0
            else:
                start = self.int_w(self.convert_type(
                    w_idx.w_start, self.w_fixnum, "to_int"))
            if w_idx.w_end is self.w_nil:
                end = length
            else:
                end = self.int_w(self.convert_type(
                    w_idx.w_end, self.w_fixnum, "to_int"))
                inclusive = not w_idx.exclusive
            as_range = True
        else:
            start = self.int_w(self.convert_type(
                w_idx, self.w_fixnum, "to_int"))
            if w_count:
                end = self.int_w(self.convert_type(
                    w_count, self.w_fixnum, "to_int"))
                if end >= 0:
                    as_range = True
                else:
                    if start < 0:
                        start += length
                    return (start, end, False, True)

        if start < 0:
            start += length

        if as_range:
            if w_count:
                end += start
            if end < 0:
                end += length
            if inclusive:
                end += 1
            if end < start:
                end = start
            elif end > length:
                end = length
            nil = start < 0 or end < 0 or start > length
        else:
            nil = start < 0 or start >= length

        return (start, end, as_range, nil)

    def convert_type(self, w_obj, w_cls, method, raise_error=True,
                     reraise_error=False):
        if self.is_kind_of(w_obj, w_cls):
            return w_obj

        w_res = self.check_funcall(w_obj, method, reraise_error)
        if w_res is None:
            if not raise_error:
                return self.w_nil
            raise self.error(
                self.w_TypeError, self.implicit_conversion_message(w_obj, w_cls))

        if w_res is self.w_nil and not raise_error:
            return self.w_nil
        elif not self.is_kind_of(w_res, w_cls):
            src_cls = self.obj_to_s(self.getclass(w_obj))
            res_cls = self.obj_to_s(self.getclass(w_res))
            w_cls_name = self.obj_to_s(w_cls)
            raise self.error(
                self.w_TypeError,
                "can't convert %s to %s (%s#%s gives %s)" % (
                    src_cls, w_cls_name, src_cls, method, res_cls))
        else:
            return w_res

    def check_funcall(self, w_obj, method, reraise_error=False):
        """MRI's rb_check_funcall: w_obj.method() if w_obj has the method,
        else None. An object that lacks the method (and does not claim it
        through respond_to_missing?, or has no method_missing of its own)
        is not asked, so a failed conversion costs no NoMethodError: Rails
        probes to_ary/to_str/to_hash tens of thousands of times a request.
        Only a method_missing of the object's own gets called, and only its
        NoMethodError for this very method is swallowed; other errors (and
        errors from a method that exists) propagate, as in MRI."""
        from topaz.objects.exceptionobject import W_NoMethodError
        from topaz.objects.functionobject import W_BuiltinFunction
        w_cls = self.getclass(w_obj)
        raw_method = w_cls.find_method(self, method)
        if raw_method is not None and not raw_method.is_undefined():
            return raw_method.call(self, w_obj, [], None)
        w_rtm = w_cls.find_method(self, "respond_to_missing?")
        if w_rtm is not None and not isinstance(w_rtm, W_BuiltinFunction):
            w_claims = w_rtm.call(
                self, w_obj, [self.newsymbol(method), self.w_true], None)
            if not self.is_true(w_claims):
                return None
        w_mm = w_cls.find_method(self, "method_missing")
        if w_mm is None or isinstance(w_mm, W_BuiltinFunction):
            return None
        try:
            return w_mm.call(self, w_obj, [self.newsymbol(method)], None)
        except RubyError as e:
            if reraise_error:
                raise
            w_exc = e.w_value
            if (isinstance(w_exc, W_NoMethodError) and
                    isinstance(w_exc.w_name, W_SymbolObject) and
                    self.symbol_w(w_exc.w_name) == method):
                self.mark_topframe_not_escaped()
                return None
            raise

    def implicit_conversion_message(self, w_obj, w_cls):
        """Ruby's TypeError message for an object that does not convert
        implicitly (to_int, to_str, to_ary, ...) to w_cls."""
        w_cls_name = self.obj_to_s(w_cls)
        if w_obj is self.w_nil and w_cls_name == "Integer":
            return "no implicit conversion from nil to integer"
        if w_obj is self.w_nil:
            src = "nil"
        elif w_obj is self.w_true:
            src = "true"
        elif w_obj is self.w_false:
            src = "false"
        else:
            src = self.obj_to_s(self.getnonsingletonclass(w_obj))
        return "no implicit conversion of %s into %s" % (src, w_cls_name)

    def mark_topframe_not_escaped(self):
        self.getexecutioncontext().gettopframe().set_escaped(False)

    def infect(self, w_dest, w_src, taint=True, untrust=True, freeze=False):
        """
        By default copies tainted and untrusted state from src to dest.
        Frozen state isn't copied by default, as this is the rarer case MRI.
        """
        if taint and self.is_true(w_src.get_flag(self, "tainted?")):
            w_dest.set_flag(self, "tainted?")
        if untrust and self.is_true(w_src.get_flag(self, "untrusted?")):
            w_dest.set_flag(self, "untrusted?")
        if freeze and self.is_true(w_src.get_flag(self, "frozen?")):
            w_dest.set_flag(self, "frozen?")

    def getaddrstring(self, w_obj):
        w_id = self.newint_or_bigint(compute_unique_id(w_obj))
        w_4 = self.newint(4)
        w_0x0F = self.newint(0x0F)
        i = 2 * rffi.sizeof(llmemory.Address)
        addrstring = [" "] * i
        while True:
            n = self.int_w(self.send(w_id, "&", [w_0x0F]))
            n += ord("0")
            if n > ord("9"):
                n += (ord("a") - ord("9") - 1)
            i -= 1
            addrstring[i] = chr(n)
            if i == 0:
                break
            w_id = self.send(w_id, ">>", [w_4])
        return "".join(addrstring)

    def any_to_s(self, w_obj):
        return "#<%s:0x%s>" % (
            self.obj_to_s(self.getnonsingletonclass(w_obj)),
            self.getaddrstring(w_obj)
        )

    def obj_to_s(self, w_obj):
        return self.str_w(self.send(w_obj, "to_s"))

    def describe_receiver(self, w_obj):
        """How error messages name an object since Ruby 3.4: "nil", "main",
        "class Foo", "module Bar" or "an instance of Baz"."""
        if w_obj is self.w_nil:
            return "nil"
        elif w_obj is self.w_true:
            return "true"
        elif w_obj is self.w_false:
            return "false"
        elif w_obj is self.w_top_self:
            return "main"
        elif isinstance(w_obj, W_ClassObject):
            return "class %s" % self.obj_to_s(w_obj)
        elif isinstance(w_obj, W_ModuleObject):
            return "module %s" % self.obj_to_s(w_obj)
        return "an instance of %s" % self.obj_to_s(
            self.getnonsingletonclass(w_obj))

    def undefined_method_error(self, name, w_receiver):
        error = self.error(
            self.w_NoMethodError,
            "undefined method '%s' for %s" % (
                name, self.describe_receiver(w_receiver)))
        self.set_name_error_details(error.w_value, name, w_receiver)
        return error

    def set_name_error_details(self, w_error, name, w_receiver):
        """NameError#name and #receiver."""
        from topaz.objects.exceptionobject import W_NameError
        if isinstance(w_error, W_NameError):
            w_error.w_name = self.newsymbol(name)
        w_error.set_instance_var(self, "@__topaz_receiver", w_receiver)

    def compare(self, w_a, w_b, block=None):
        if block is None:
            w_cmp_res = self.send(w_a, "<=>", [w_b])
        else:
            w_cmp_res = self.invoke_block(block, [w_a, w_b])
        if w_cmp_res is self.w_nil:
            raise self.error(
                self.w_ArgumentError,
                "comparison of %s with %s failed" % (
                    self.obj_to_s(self.getclass(w_a)),
                    self.obj_to_s(self.getclass(w_b)),
                )
            )
        else:
            return w_cmp_res
