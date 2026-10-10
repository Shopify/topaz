from rpython.rlib import jit, rstackovf, rvmprof
from rpython.rlib.debug import check_nonneg
from rpython.rlib.objectmodel import we_are_translated

from topaz import consts
from topaz.error import RubyError
from topaz.objects.arrayobject import W_ArrayObject
from topaz.objects.classobject import W_ClassObject
from topaz.objects.codeobject import W_CodeObject, UnwindHandler
from topaz.objects.functionobject import W_FunctionObject
from topaz.objects.hashobject import W_HashObject
from topaz.objects.moduleobject import W_ModuleObject
from topaz.objects.objectobject import W_Root
from topaz.objects.procobject import W_ProcObject
from topaz.scope import StaticScope
from topaz.utils.regexp import RegexpError


def get_printable_location(pc, bytecode, w_trace_proc):
    try:
        pcline = bytecode.lineno_table[pc]
    except IndexError:
        pcline = -1
    return "%s:%d(%d):in %s at %s" % (
        bytecode.filepath,
        bytecode.lineno,
        pcline,
        bytecode.name,
        consts.BYTECODE_NAMES[ord(bytecode.code[pc])]
    )


def get_unique_id(pc, bytecode, w_trace_proc):
    return rvmprof.get_unique_id(bytecode)


def promote_unless_virtual(obj):
    """Promote obj, unless the trace allocated it: promoting a virtual
    (instance_exec makes a new StaticScope per call) makes the optimizer
    reject the whole trace, so it could never be compiled."""
    if jit.isvirtual(obj):
        return obj
    return jit.promote(obj)


def _get_vmprof_code(self, space, frame, bytecode, pc):
    return bytecode


class Interpreter(object):
    # The block passed to a method is deliberately not a green: with it,
    # every (method, call-site block) pair was a separate trace with its own
    # counters, so a Rails method called with blocks from N sites needed N
    # times the calls to compile and was traced N times. create_frame
    # promotes the block's bytecode when it is yielded to, so the trace tree
    # still specializes on the block, only at the yield instead of at the
    # entry. lobsters at 40 iterations: 1059ms -> 978/980ms per iteration,
    # total run 66s -> 63-64s, MAXRSS 1119 -> 1087MiB.
    jitdriver = jit.JitDriver(
        greens=["pc", "bytecode", "w_trace_proc"],
        reds=["self", "frame"],
        virtualizables=["frame"],
        get_printable_location=get_printable_location,
        get_unique_id=get_unique_id,
        check_untranslated=False,
        is_recursive=True
    )

    def __init__(self):
        self.finished = False

    # RPython's stacklet support (used for Fibers) always links in rvmprof,
    # which requires the interpreter to declare its code-executing function.
    # This also makes Ruby frames visible to vmprof.
    @rvmprof.vmprof_execute_code("topaz", _get_vmprof_code)
    def interpret(self, space, frame, bytecode, pc):
        if not jit.we_are_jitted() and space.interp_profile.enabled:
            if bytecode.interp_entries == 0 and bytecode.interp_instrs == 0:
                space.interp_profile.codes_w.append(bytecode)
            bytecode.interp_entries += 1
        try:
            while True:
                self.jitdriver.jit_merge_point(
                    self=self, bytecode=bytecode, frame=frame, pc=pc,
                    w_trace_proc=space.getexecutioncontext().gettraceproc(),
                )
                pc = self._interpret(space, pc, frame, bytecode)
        except RaiseReturn as e:
            if e.parent_interp is self:
                return e.w_value
            raise
        except Return as e:
            return e.w_value

    def run(self, space, frame, bytecode, entry_pc=0):
        """Runs the frame, then marks this interpreter finished (so that a
        break from one of its blocks is known to be an orphan). The mark is
        made here, outside the JIT's portal: made in interpret's own
        finally clause, the translated JIT marked the wrong interpreter
        finished after a break left an inlined call, and a later break
        from the same method raised "break from proc-closure"."""
        try:
            # Past the defaults of the optional arguments that were passed:
            # the pc is an argument of the portal, so a green.
            return self.interpret(space, frame, bytecode, entry_pc)
        finally:
            self.finished = True

    def _interpret(self, space, pc, frame, bytecode):
        if not jit.we_are_jitted() and space.interp_profile.enabled:
            if bytecode.interp_entries == 0 and bytecode.interp_instrs == 0:
                space.interp_profile.codes_w.append(bytecode)
            bytecode.interp_instrs += 1
        prev_pc = frame.last_instr
        frame.last_instr = pc
        try:
            if (space.getexecutioncontext().hastraceproc() and
                    bytecode.lineno_table[pc] != bytecode.lineno_table[prev_pc]):
                space.getexecutioncontext().invoke_trace_proc(
                    space, "line", None, None, frame=frame)
            pc = self.handle_bytecode(space, pc, frame, bytecode)
        except RubyError as e:
            pc = self.handle_ruby_error(space, pc, frame, bytecode, e)
        except RaiseReturn as e:
            pc = self.handle_raise_return(space, pc, frame, bytecode, e)
        except RaiseBreak as e:
            pc = self.handle_raise_break(space, pc, frame, bytecode, e)
        except Throw as e:
            pc = self.handle_throw(space, pc, frame, bytecode, e)
        except rstackovf.StackOverflow:
            rstackovf.check_stack_overflow()
            pc = self.handle_ruby_error(
                space, pc, frame, bytecode,
                space.error(space.w_SystemStackError, "stack level too deep"))
        return pc

    def handle_bytecode(self, space, pc, frame, bytecode):
        start_pc = pc
        instr = ord(bytecode.code[pc])
        pc += 1
        num_args = consts.BYTECODE_NUM_ARGS[instr]
        arg0 = 0
        arg1 = 0
        # Do not change these from * 256 to << 8, lshift has defined overflow
        # semantics which cause it to not propagate the nonnegative-ness.
        if num_args >= 1:
            arg0 = ord(bytecode.code[pc]) | (ord(bytecode.code[pc + 1]) * 256)
            check_nonneg(arg0)
            pc += 2
        if num_args >= 2:
            arg1 = ord(bytecode.code[pc]) | (ord(bytecode.code[pc + 1]) * 256)
            check_nonneg(arg1)
            pc += 2
        if num_args >= 3:
            raise NotImplementedError

        # Control-transfer opcodes need the instruction-start PC. Other
        # methods retain the advanced PC used for calls and backtraces.
        method_pc = pc
        if instr in (consts.RETURN, consts.RAISE_RETURN, consts.RAISE_BREAK,
                     consts.BREAK_LOOP, consts.CONTINUE_LOOP):
            method_pc = start_pc
        try:
            if we_are_translated():
                for i, name in consts.UNROLLING_BYTECODES:
                    if i == instr:
                        method = getattr(self, name)
                        n = consts.BYTECODE_NUM_ARGS[i]
                        if n == 0:
                            res = method(space, bytecode, frame, method_pc)
                        elif n == 1:
                            res = method(space, bytecode, frame, method_pc, arg0)
                        else:
                            res = method(space, bytecode, frame, method_pc, arg0, arg1)
                        if res is not None:
                            pc = res
                        break
                else:
                    raise SystemError
            else:
                method = getattr(self, consts.BYTECODE_NAMES[instr])
                args = [arg0, arg1][:num_args]
                res = method(space, bytecode, frame, method_pc, *args)
                if res is not None:
                    pc = res
        except RaiseBreak as e:
            if e.parent_interp is not self:
                raise
            frame.push(e.w_value)
        return pc

    def handle_ruby_error(self, space, pc, frame, bytecode, e):
        block = self.find_handler(bytecode, frame, bytecode.handler_at(pc), ApplicationException.kind)
        if block is None:
            raise e
        unroller = ApplicationException(e)
        return self.enter_handler(space, bytecode, frame, block, unroller)

    def handle_raise_return(self, space, pc, frame, bytecode, e):
        block = self.find_handler(bytecode, frame, bytecode.handler_at(pc), RaiseReturnValue.kind)
        if block is None:
            raise e
        unroller = RaiseReturnValue(e.parent_interp, e.w_value)
        return self.enter_handler(space, bytecode, frame, block, unroller)

    def handle_raise_break(self, space, pc, frame, bytecode, e):
        block = self.find_handler(bytecode, frame, bytecode.handler_at(pc), RaiseBreakValue.kind)
        if block is None:
            raise e
        unroller = RaiseBreakValue(e.parent_interp, e.w_value)
        return self.enter_handler(space, bytecode, frame, block, unroller)

    def handle_throw(self, space, pc, frame, bytecode, e):
        block = self.find_handler(bytecode, frame, bytecode.handler_at(pc), ThrowValue.kind)
        if block is None:
            raise e
        unroller = ThrowValue(e.name, e.w_value)
        return self.enter_handler(space, bytecode, frame, block, unroller)

    def jump(self, space, bytecode, frame, cur_pc, target_pc):
        if target_pc < cur_pc:
            self.jitdriver.can_enter_jit(
                self=self, bytecode=bytecode, frame=frame, pc=target_pc,
                w_trace_proc=space.getexecutioncontext().gettraceproc()
            )
        return target_pc

    def LOAD_SELF(self, space, bytecode, frame, pc):
        w_self = frame.w_self
        jit.promote(space.getclass(w_self))
        frame.push(w_self)

    def LOAD_SCOPE(self, space, bytecode, frame, pc):
        scope = frame.lexical_scope
        if scope is not None:
            if scope.w_singleton_of is not None:
                frame.push(space.getsingletonclass(scope.w_singleton_of))
            else:
                frame.push(scope.w_mod)
        else:
            frame.push(space.w_object)

    def LOAD_BLOCK(self, space, bytecode, frame, pc):
        frame.push(frame.block or space.w_nil)

    def LOAD_CODE(self, space, bytecode, frame, pc):
        frame.push(bytecode)

    def LOAD_CONST(self, space, bytecode, frame, pc, idx):
        frame.push(bytecode.consts_w[idx])

    def LOAD_DEREF(self, space, bytecode, frame, pc, idx):
        frame.push(frame.get_cell(idx).get(space, frame, idx) or space.w_nil)

    def STORE_DEREF(self, space, bytecode, frame, pc, idx):
        frame.get_cell(idx).set(space, frame, idx, frame.peek())

    def LOAD_CLOSURE(self, space, bytecode, frame, pc, idx):
        frame.push(frame.get_cell(idx).upgrade_to_closure(space, frame, idx))

    def LOAD_CONSTANT(self, space, bytecode, frame, pc, idx):
        space.getexecutioncontext().last_instr = pc
        w_scope = frame.pop()
        w_name = bytecode.consts_w[idx]
        name = space.symbol_w(w_name)
        if not isinstance(w_scope, W_ModuleObject):
            raise space.error(space.w_TypeError,
                "%s is not a class/module" % space.str_w(space.send(w_scope, "inspect")))
        w_obj = w_scope.find_scoped_const(space, name)
        if w_obj is None:
            w_obj = space.send(w_scope, "const_missing", [space.newsymbol(name)])
        frame.push(w_obj)

    def STORE_CONSTANT(self, space, bytecode, frame, pc, idx):
        space.getexecutioncontext().last_instr = pc
        w_name = bytecode.consts_w[idx]
        name = space.symbol_w(w_name)
        w_value = frame.pop()
        w_scope = frame.pop()
        space.set_const(w_scope, name, w_value)
        frame.push(w_value)

    def DEFINED_CONSTANT(self, space, bytecode, frame, pc, idx):
        space.getexecutioncontext().last_instr = pc
        w_name = bytecode.consts_w[idx]
        w_scope = frame.pop()
        # `defined?(Mod::Name)` looks where `Mod::Name` does (not in
        # Object, for a module), without autoloading.
        if (isinstance(w_scope, W_ModuleObject) and
                w_scope.find_scoped_const(space, space.symbol_w(w_name), autoload=False) is not None):
            frame.push(space.newstr_fromstr("constant"))
        else:
            frame.push(space.w_nil)

    def LOAD_LOCAL_CONSTANT(self, space, bytecode, frame, pc, idx):
        space.getexecutioncontext().last_instr = pc
        frame.pop()
        w_name = bytecode.consts_w[idx]
        name = space.symbol_w(w_name)
        frame.push(space.find_lexical_const(
            promote_unless_virtual(frame.lexical_scope), name))

    @jit.unroll_safe
    def DEFINED_LOCAL_CONSTANT(self, space, bytecode, frame, pc, idx):
        space.getexecutioncontext().last_instr = pc
        frame.pop()
        w_name = bytecode.consts_w[idx]
        name = space.symbol_w(w_name)
        w_res = space._find_lexical_const(
            promote_unless_virtual(frame.lexical_scope), name, autoload=False)
        if w_res is None:
            frame.push(space.w_nil)
        else:
            frame.push(space.newstr_fromstr("constant"))

    def LOAD_INSTANCE_VAR(self, space, bytecode, frame, pc, idx):
        w_name = bytecode.consts_w[idx]
        w_obj = frame.pop()
        w_res = (space.find_instance_var(w_obj, space.symbol_w(w_name)) or
                 space.w_nil)
        frame.push(w_res)

    def STORE_INSTANCE_VAR(self, space, bytecode, frame, pc, idx):
        w_name = bytecode.consts_w[idx]
        w_value = frame.pop()
        w_obj = frame.pop()
        space.set_instance_var(w_obj, space.symbol_w(w_name), w_value)
        frame.push(w_value)

    def DEFINED_INSTANCE_VAR(self, space, bytecode, frame, pc, idx):
        space.getexecutioncontext().last_instr = pc
        w_name = bytecode.consts_w[idx]
        w_obj = frame.pop()
        if space.is_true(space.send(
                w_obj, "instance_variable_defined?", [w_name])):
            frame.push(space.newstr_fromstr("instance-variable"))
        else:
            frame.push(space.w_nil)

    def _class_var_base(self, scope, w_module):
        """Class variables are not looked up in singleton classes: code in
        `class << self` uses the enclosing class's."""
        if not (isinstance(w_module, W_ClassObject) and w_module.is_singleton):
            return w_module
        while scope is not None:
            w_mod = scope.w_mod
            if not (isinstance(w_mod, W_ClassObject) and w_mod.is_singleton):
                return w_mod
            scope = scope.backscope
        return w_module

    def LOAD_CLASS_VAR(self, space, bytecode, frame, pc, idx):
        name = space.symbol_w(bytecode.consts_w[idx])
        w_module = frame.pop()
        assert isinstance(w_module, W_ModuleObject)
        w_module = self._class_var_base(frame.lexical_scope, w_module)
        w_value = space.find_class_var(w_module, name)
        frame.push(w_value)

    def STORE_CLASS_VAR(self, space, bytecode, frame, pc, idx):
        name = space.symbol_w(bytecode.consts_w[idx])
        w_value = frame.pop()
        w_module = frame.pop()
        assert isinstance(w_module, W_ModuleObject)
        w_module = self._class_var_base(frame.lexical_scope, w_module)
        space.set_class_var(w_module, name, w_value)
        frame.push(w_value)

    def DEFINED_CLASS_VAR(self, space, bytecode, frame, pc, idx):
        space.getexecutioncontext().last_instr = pc
        w_name = bytecode.consts_w[idx]
        w_obj = frame.pop()
        if space.is_true(space.send(
                w_obj, "class_variable_defined?", [w_name])):
            frame.push(space.newstr_fromstr("class variable"))
        else:
            frame.push(space.w_nil)

    def LOAD_GLOBAL(self, space, bytecode, frame, pc, idx):
        space.getexecutioncontext().last_instr = pc
        name = space.symbol_w(bytecode.consts_w[idx])
        w_value = space.globals.get(space, name) or space.w_nil
        frame.push(w_value)

    def STORE_GLOBAL(self, space, bytecode, frame, pc, idx):
        space.getexecutioncontext().last_instr = pc
        name = space.symbol_w(bytecode.consts_w[idx])
        w_value = frame.peek()
        space.globals.set(space, name, w_value)

    def DEFINED_GLOBAL(self, space, bytecode, frame, pc, idx):
        name = space.symbol_w(bytecode.consts_w[idx])
        if space.globals.get(space, name) is not None:
            frame.push(space.newstr_fromstr("global-variable"))
        else:
            frame.push(space.w_nil)

    def BUILD_ARRAY(self, space, bytecode, frame, pc, n_items):
        items_w = frame.popitemsreverse(n_items)
        frame.push(space.newarray(items_w))

    @jit.unroll_safe
    def BUILD_ARRAY_SPLAT(self, space, bytecode, frame, pc, n_items):
        arrays_w = frame.popitemsreverse(n_items)
        items_w = []
        for w_array in arrays_w:
            items_w.extend(space.listview(w_array))
        frame.push(space.newarray(items_w))

    def BUILD_STRING(self, space, bytecode, frame, pc, n_items):
        items_w = frame.popitemsreverse(n_items)
        frame.push(space.newstr_fromstrs(items_w))

    def BUILD_HASH(self, space, bytecode, frame, pc):
        frame.push(space.newhash())

    def MARK_KEYWORDS(self, space, bytecode, frame, pc):
        w_hash = frame.peek()
        if isinstance(w_hash, W_HashObject):
            w_hash.is_keywords = True

    def BUILD_RANGE(self, space, bytecode, frame, pc):
        w_end = frame.pop()
        w_start = frame.pop()
        w_range = space.newrange(w_start, w_end, False)
        frame.push(w_range)

    def BUILD_RANGE_EXCLUSIVE(self, space, bytecode, frame, pc):
        w_end = frame.pop()
        w_start = frame.pop()
        w_range = space.newrange(w_start, w_end, True)
        frame.push(w_range)

    def BUILD_FUNCTION(self, space, bytecode, frame, pc):
        w_code = frame.pop()
        w_name = frame.pop()
        w_func = space.newfunction(
            w_name, w_code, frame.lexical_scope, frame.get_visibility())
        frame.push(w_func)

    @jit.unroll_safe
    def BUILD_BLOCK(self, space, bytecode, frame, pc, n_cells):
        cells = [frame.pop() for _ in range(n_cells)]
        w_code = frame.pop()
        assert isinstance(w_code, W_CodeObject)
        w_proc = space.newproc(
            w_code, frame.w_self, frame.lexical_scope, cells, frame.block,
            self, frame.top_parent_interp or self, frame.get_regexp_match_cell()
        )
        w_proc.super_context = frame.super_context
        frame.push(w_proc)

    def BUILD_LAMBDA(self, space, bytecode, frame, pc):
        block = frame.pop()
        assert isinstance(block, W_ProcObject)
        frame.push(block.copy(space, is_lambda=True))

    def BUILD_CLASS(self, space, bytecode, frame, pc):
        space.getexecutioncontext().last_instr = pc
        superclass = frame.pop()
        w_name = frame.pop()
        w_scope = frame.pop()

        name = space.symbol_w(w_name)
        w_cls = w_scope.find_included_const(space, name, autoload=True)
        if w_cls is None:
            if superclass is space.w_nil:
                superclass = space.w_object
            if not space.is_kind_of(superclass, space.w_class):
                cls_name = space.obj_to_s(space.getclass(superclass))
                raise space.error(
                    space.w_TypeError,
                    "wrong argument type %s (expected Class)" % cls_name)
            assert isinstance(superclass, W_ClassObject)
            if superclass.is_singleton:
                raise space.error(
                    space.w_TypeError,
                    "can't make subclass of singleton class")
            w_cls = space.newclass(name, superclass, w_scope=w_scope)
            space.set_const(w_scope, name, w_cls)
        elif not space.is_kind_of(w_cls, space.w_class):
            raise space.error(space.w_TypeError, "%s is not a class" % name)
        else:
            assert isinstance(w_cls, W_ClassObject)
            if (superclass is not space.w_nil and
                    w_cls.superclass is not superclass):
                raise space.error(
                    space.w_TypeError,
                    "superclass mismatch for class %s" % w_cls.name)

        frame.push(w_cls)

    def BUILD_MODULE(self, space, bytecode, frame, pc):
        space.getexecutioncontext().last_instr = pc
        w_name = frame.pop()
        w_scope = frame.pop()

        name = space.symbol_w(w_name)
        w_mod = w_scope.find_included_const(space, name, autoload=True)

        if w_mod is None:
            w_mod = space.newmodule(name, w_scope=w_scope)
            space.set_const(w_scope, name, w_mod)
        elif (not space.is_kind_of(w_mod, space.w_module) or
                space.is_kind_of(w_mod, space.w_class)):
            raise space.error(space.w_TypeError, "%s is not a module" % name)

        frame.push(w_mod)

    def BUILD_REGEXP(self, space, bytecode, frame, pc):
        w_flags = frame.pop()
        w_string = frame.pop()
        try:
            w_regexp = space.newregexp(
                space.str_w(w_string), space.int_w(w_flags))
        except RegexpError as e:
            raise space.error(space.w_RegexpError, e.msg)
        frame.push(w_regexp)

    def COERCE_ARRAY(self, space, bytecode, frame, pc, nil_is_empty):
        w_obj = frame.pop()
        if w_obj is space.w_nil:
            if nil_is_empty:
                frame.push(space.newarray([]))
            else:
                frame.push(space.newarray([space.w_nil]))
        elif isinstance(w_obj, W_ArrayObject):
            frame.push(w_obj)
        else:
            space.getexecutioncontext().last_instr = pc
            if space.respond_to(w_obj, "to_a"):
                w_res = space.send(w_obj, "to_a")
            elif space.respond_to(w_obj, "to_ary"):
                w_res = space.send(w_obj, "to_ary")
            else:
                w_res = space.newarray([w_obj])
            if not isinstance(w_res, W_ArrayObject):
                w_res = space.newarray([w_obj])
            frame.push(w_res)

    def COERCE_BLOCK(self, space, bytecode, frame, pc):
        w_block = frame.pop()
        if w_block is space.w_nil:
            frame.push(w_block)
        elif isinstance(w_block, W_ProcObject):
            frame.push(w_block)
        elif space.respond_to(w_block, "to_proc"):
            space.getexecutioncontext().last_instr = pc
            # Proc implements to_proc, too, but MRI doesn't call it
            w_res = space.convert_type(w_block, space.w_proc, "to_proc")
            assert isinstance(w_res, W_ProcObject)
            frame.push(w_res)
        else:
            raise space.error(space.w_TypeError, "wrong argument type")

    def COERCE_STRING(self, space, bytecode, frame, pc):
        w_symbol = frame.pop()
        frame.push(space.newstr_fromstr(space.symbol_w(w_symbol)))

    @jit.unroll_safe
    def UNPACK_SEQUENCE(self, space, bytecode, frame, pc, n_items):
        w_obj = frame.pop()
        items_w = space.listview(w_obj)
        for i in xrange(n_items - 1, -1, -1):
            try:
                w_obj = items_w[i]
            except IndexError:
                w_obj = space.w_nil
            frame.push(w_obj)

    @jit.unroll_safe
    def UNPACK_SEQUENCE_SPLAT(
            self, space, bytecode, frame, pc, n_targets, n_pre):
        w_obj = frame.pop()
        items_w = space.listview(w_obj)
        n_items = len(items_w)
        n_post = n_targets - n_pre - 1
        n_splat = max(n_items - n_pre - n_post, 0)
        for i in xrange(n_items, n_pre + n_splat + n_post, 1):
            items_w.append(space.w_nil)

        for i in xrange(n_pre + n_splat + n_post - 1, n_pre + n_splat - 1, -1):
            frame.push(items_w[i])
        splat_array = [items_w[i] for i in xrange(n_pre, n_pre + n_splat, 1)]
        frame.push(space.newarray(splat_array))
        for i in xrange(n_pre - 1, -1, -1):
            frame.push(items_w[i])

    def DEFINE_FUNCTION(self, space, bytecode, frame, pc):
        w_func = frame.pop()
        w_name = frame.pop()
        w_scope = frame.pop()
        assert isinstance(w_func, W_FunctionObject)
        # None is special case. It means that we are trying to define
        # a method on Symbol or Numeric.
        if w_scope is None:
            raise space.error(
                space.w_TypeError,
                """can't define singleton method "%s" for %s""" % (
                    space.symbol_w(w_name), space.getclass(frame.w_self).name))
        w_scope.define_method(space, space.symbol_w(w_name), w_func)
        # `def` evaluates to the method's name (Ruby 2.1).
        frame.push(w_name)

    def ATTACH_FUNCTION(self, space, bytecode, frame, pc):
        w_func = frame.pop()
        w_name = frame.pop()
        w_obj = frame.pop()
        if (space.is_kind_of(w_obj, space.w_symbol) or
                space.is_kind_of(w_obj, space.w_numeric)):
            raise space.error(
                space.w_TypeError, "no class/module to add method")
        assert isinstance(w_func, W_FunctionObject)
        w_obj.attach_method(space, space.symbol_w(w_name), w_func)
        frame.push(w_name)

    def EVALUATE_MODULE(self, space, bytecode, frame, pc):
        space.getexecutioncontext().last_instr = pc
        w_bytecode = frame.pop()
        w_mod = frame.pop()
        assert isinstance(w_bytecode, W_CodeObject)

        event = "class" if space.is_kind_of(w_mod, space.w_class) else "module"
        space.getexecutioncontext().invoke_trace_proc(
            space, event, None, None, frame=frame)
        sub_frame = space.create_frame(
            w_bytecode, w_mod, StaticScope(w_mod, frame.lexical_scope),
            block=frame.block)
        with space.getexecutioncontext().visit_frame(sub_frame):
            w_res = space.execute_frame(sub_frame, w_bytecode)

        space.getexecutioncontext().invoke_trace_proc(
            space, "end", None, None, frame=frame)
        frame.push(w_res)

    def LOAD_SINGLETON_CLASS(self, space, bytecode, frame, pc):
        w_obj = frame.pop()
        if (space.is_kind_of(w_obj, space.w_symbol) or
                space.is_kind_of(w_obj, space.w_fixnum)):
            raise space.error(space.w_TypeError, "can't define singleton")
        frame.push(space.getsingletonclass(w_obj))

    def SEND(self, space, bytecode, frame, pc, meth_idx, num_args):
        space.getexecutioncontext().last_instr = pc
        w_res = space.send_valuestack(
            space.symbol_w(bytecode.consts_w[meth_idx]), num_args, frame)
        frame.push(w_res)

    def SEND_BLOCK(self, space, bytecode, frame, pc, meth_idx, num_args):
        space.getexecutioncontext().last_instr = pc
        w_block = frame.pop()
        args_w = frame.popitemsreverse(num_args - 1)
        w_receiver = frame.pop()
        if w_block is space.w_nil:
            w_block = None
        else:
            assert isinstance(w_block, W_ProcObject)
        w_res = space.send(
            w_receiver, space.symbol_w(bytecode.consts_w[meth_idx]), args_w,
            block=w_block)
        frame.push(w_res)

    @jit.unroll_safe
    def SEND_SPLAT(self, space, bytecode, frame, pc, meth_idx, num_args):
        space.getexecutioncontext().last_instr = pc
        arrays_w = frame.popitemsreverse(num_args)
        length = 0
        for w_array in arrays_w:
            length += len(space.listview(w_array))
        args_w = [None] * length
        pos = 0
        for w_array in arrays_w:
            array_w = space.listview(w_array)
            args_w[pos:pos + len(array_w)] = array_w
            pos += len(array_w)
        w_receiver = frame.pop()
        w_res = space.send(
            w_receiver, space.symbol_w(bytecode.consts_w[meth_idx]), args_w)
        frame.push(w_res)

    @jit.unroll_safe
    def SEND_BLOCK_SPLAT(self, space, bytecode, frame, pc, meth_idx, num_args):
        space.getexecutioncontext().last_instr = pc
        w_block = frame.pop()
        arrays_w = frame.popitemsreverse(num_args - 1)
        args_w = []
        for w_array in arrays_w:
            args_w.extend(space.listview(w_array))
        w_receiver = frame.pop()
        if w_block is space.w_nil:
            w_block = None
        else:
            assert isinstance(w_block, W_ProcObject)
        w_res = space.send(
            w_receiver, space.symbol_w(bytecode.consts_w[meth_idx]), args_w,
            block=w_block)
        frame.push(w_res)

    def DEFINED_METHOD(self, space, bytecode, frame, pc, meth_idx):
        space.getexecutioncontext().last_instr = pc
        w_obj = frame.pop()
        if space.respond_to(
                w_obj, space.symbol_w(bytecode.consts_w[meth_idx])):
            frame.push(space.newstr_fromstr("method"))
        else:
            frame.push(space.w_nil)

    def _super_name(self, space, bytecode, frame, meth_idx):
        context = frame.super_context
        if context is not None:
            name = context.name
            if name is not None:
                return name
        return space.symbol_w(bytecode.consts_w[meth_idx])

    def SEND_SUPER_BLOCK(self, space, bytecode, frame, pc, meth_idx, num_args):
        space.getexecutioncontext().last_instr = pc
        w_block = frame.pop()
        args_w = frame.popitemsreverse(num_args - 1)
        w_receiver = frame.pop()
        if w_block is space.w_nil:
            w_block = None
        else:
            assert isinstance(w_block, W_ProcObject)
        w_owner = frame.get_super_owner()
        if w_owner is None and frame.lexical_scope is not None:
            w_owner = frame.lexical_scope.w_mod
        if w_owner is not None:
            w_res = space.send_super_from(
                w_owner, w_receiver,
                self._super_name(space, bytecode, frame, meth_idx), args_w,
                block=w_block, context=frame.super_context)
        else:
            w_res = space.send_super(
                space.getclass(w_receiver), w_receiver,
                self._super_name(space, bytecode, frame, meth_idx), args_w,
                block=w_block)
        frame.push(w_res)

    @jit.unroll_safe
    def SEND_SUPER_BLOCK_SPLAT(
            self, space, bytecode, frame, pc, meth_idx, num_args):
        space.getexecutioncontext().last_instr = pc
        w_block = frame.pop()
        arrays_w = frame.popitemsreverse(num_args - 1)
        args_w = []
        for w_array in arrays_w:
            args_w.extend(space.listview(w_array))
        w_receiver = frame.pop()
        if w_block is space.w_nil:
            w_block = None
        else:
            assert isinstance(w_block, W_ProcObject)
        w_owner = frame.get_super_owner()
        if w_owner is None and frame.lexical_scope is not None:
            w_owner = frame.lexical_scope.w_mod
        if w_owner is not None:
            w_res = space.send_super_from(
                w_owner, w_receiver,
                self._super_name(space, bytecode, frame, meth_idx), args_w,
                block=w_block, context=frame.super_context)
        else:
            w_res = space.send_super(
                space.getclass(w_receiver), w_receiver,
                self._super_name(space, bytecode, frame, meth_idx), args_w,
                block=w_block)
        frame.push(w_res)

    def DEFINED_SUPER(self, space, bytecode, frame, pc, meth_idx):
        space.getexecutioncontext().last_instr = pc
        w_obj = frame.pop()
        name = space.symbol_w(bytecode.consts_w[meth_idx])
        w_cls = space.getclass(w_obj)
        w_owner = frame.get_super_owner()
        if w_owner is None and frame.lexical_scope is not None:
            w_owner = frame.lexical_scope.w_mod
        if w_owner is not None:
            entry = None
            if frame.super_context is not None:
                entry = frame.super_context.entry
            w_method = w_cls.find_method_after(space, w_owner, name, entry)
        else:
            w_method = w_cls.find_method_super(space, name)
        if w_method is not None:
            frame.push(space.newstr_fromstr("super"))
        else:
            frame.push(space.w_nil)

    @jit.unroll_safe
    def find_handler(self, bytecode, frame, head, kind):
        while head >= 0:
            handler = bytecode.unwind_handlers[head]
            if (handler.kind == UnwindHandler.ENSURE or
                    (handler.kind == UnwindHandler.RESCUE and
                     kind == ApplicationException.kind) or
                    (handler.kind == UnwindHandler.LOOP and
                     kind & (ContinueLoop.kind | BreakLoop.kind))):
                return handler
            self.clear_stack(frame, handler.stackdepth)
            head = handler.parent
        self.clear_stack(frame, 0)
        return None

    def clear_stack(self, frame, depth):
        # An interrupted instruction may already have popped its operands.
        # Cleanup never creates missing values.
        depth += len(frame.bytecode.cellvars)
        if frame.stackpos > depth:
            frame.dropvaluesuntil(depth)

    def enter_handler(self, space, bytecode, frame, handler, unroller):
        self.clear_stack(frame, handler.stackdepth)
        if handler.kind == UnwindHandler.LOOP:
            if isinstance(unroller, ContinueLoop):
                return unroller.target_pc
            assert isinstance(unroller, BreakLoop)
            frame.push(unroller.w_value)
        elif handler.kind == UnwindHandler.RESCUE:
            assert isinstance(unroller, ApplicationException)
            space.globals.set(space, "$!", unroller.e.w_value)
            frame.push(unroller)
            frame.push(unroller.e.w_value)
        else:
            # Both entries have [result, pending transfer, sentinel]. On
            # exceptional entry the result is unused, but occupies a real
            # initialized slot so nested handlers have one static depth.
            if isinstance(unroller, ApplicationException):
                space.globals.set(space, "$!", unroller.e.w_value)
            frame.push(space.w_nil)
            frame.push(unroller)
            frame.push(space.w_nil)
        return handler.target_pc

    def resume_unwind(self, space, bytecode, frame, head, unroller):
        handler = self.find_handler(bytecode, frame, head, unroller.kind)
        if handler is None:
            unroller.nomoreblocks()
            raise AssertionError("unroller returned")
        return self.enter_handler(space, bytecode, frame, handler, unroller)

    def END_FINALLY(self, space, bytecode, frame, pc, resume):
        frame.pop()
        unroller = frame.pop()
        if isinstance(unroller, SuspendedUnroller):
            target = self.resume_unwind(space, bytecode, frame, resume - 1, unroller)
            return self.jump(space, bytecode, frame, pc, target)
        return pc

    def CLEAR_STACK(self, space, bytecode, frame, pc, depth):
        self.clear_stack(frame, depth)

    def JUMP(self, space, bytecode, frame, pc, target_pc):
        return self.jump(space, bytecode, frame, pc, target_pc)

    def JUMP_IF_TRUE(self, space, bytecode, frame, pc, target_pc):
        if space.is_true(frame.pop()):
            return self.jump(space, bytecode, frame, pc, target_pc)
        else:
            return pc

    def JUMP_IF_KWARG_GIVEN(self, space, bytecode, frame, pc, target_pc, idx):
        if frame.is_kwarg_given(space, idx):
            return target_pc
        return pc

    def JUMP_IF_FALSE(self, space, bytecode, frame, pc, target_pc):
        if space.is_true(frame.pop()):
            return pc
        else:
            return self.jump(space, bytecode, frame, pc, target_pc)

    def DISCARD_TOP(self, space, bytecode, frame, pc):
        frame.pop()

    def DUP_TOP(self, space, bytecode, frame, pc):
        frame.push(frame.peek())

    def DUP_TWO(self, space, bytecode, frame, pc):
        w_1 = frame.pop()
        w_2 = frame.pop()
        frame.push(w_2)
        frame.push(w_1)
        frame.push(w_2)
        frame.push(w_1)

    def ROT_TWO(self, space, bytecode, frame, pc):
        w_1 = frame.pop()
        w_2 = frame.pop()
        frame.push(w_1)
        frame.push(w_2)

    def ROT_THREE(self, space, bytecode, frame, pc):
        w_1 = frame.pop()
        w_2 = frame.pop()
        w_3 = frame.pop()
        frame.push(w_1)
        frame.push(w_3)
        frame.push(w_2)

    def RETURN(self, space, bytecode, frame, pc):
        w_returnvalue = frame.pop()
        block = self.find_handler(bytecode, frame, bytecode.handler_at(pc), ReturnValue.kind)
        if block is None:
            raise Return(w_returnvalue)
        unroller = ReturnValue(w_returnvalue)
        return self.enter_handler(space, bytecode, frame, block, unroller)

    def RAISE_RETURN(self, space, bytecode, frame, pc):
        w_returnvalue = frame.pop()
        block = self.find_handler(bytecode, frame, bytecode.handler_at(pc), RaiseReturnValue.kind)
        if block is None:
            raise RaiseReturn(frame.top_parent_interp, w_returnvalue)
        unroller = RaiseReturnValue(frame.top_parent_interp, w_returnvalue)
        return self.enter_handler(space, bytecode, frame, block, unroller)

    def YIELD(self, space, bytecode, frame, pc, n_args):
        if frame.block is None:
            raise space.error(space.w_LocalJumpError, "no block given (yield)")
        space.getexecutioncontext().last_instr = pc
        args_w = frame.popitemsreverse(n_args)
        w_res = space.invoke_block(frame.block, args_w)
        frame.push(w_res)

    @jit.unroll_safe
    def YIELD_SPLAT(self, space, bytecode, frame, pc, num_args):
        if frame.block is None:
            raise space.error(space.w_LocalJumpError, "no block given (yield)")
        space.getexecutioncontext().last_instr = pc
        arrays_w = frame.popitemsreverse(num_args)
        args_w = []
        for w_array in arrays_w:
            args_w.extend(space.listview(w_array))
        w_res = space.invoke_block(frame.block, args_w)
        frame.push(w_res)

    def DEFINED_YIELD(self, space, bytecode, frame, pc):
        if frame.block is not None:
            frame.push(space.newstr_fromstr("yield"))
        else:
            frame.push(space.w_nil)

    def CONTINUE_LOOP(self, space, bytecode, frame, pc, target_pc):
        frame.pop()
        new_pc = self.resume_unwind(space, bytecode, frame, bytecode.handler_at(pc), ContinueLoop(target_pc))
        # `next` goes back to the loop's head: a loop whose iterations end
        # in `next` must count as hot too.
        return self.jump(space, bytecode, frame, pc, new_pc)

    def BREAK_LOOP(self, space, bytecode, frame, pc):
        w_obj = frame.pop()
        return self.resume_unwind(space, bytecode, frame, bytecode.handler_at(pc), BreakLoop(w_obj))

    def RAISE_BREAK(self, space, bytecode, frame, pc):
        if frame.parent_interp.finished:
            raise space.error(
                space.w_LocalJumpError, "break from proc-closure")
        w_value = frame.pop()
        block = self.find_handler(bytecode, frame, bytecode.handler_at(pc), RaiseBreakValue.kind)
        if block is None:
            raise RaiseBreak(frame.parent_interp, w_value)
        unroller = RaiseBreakValue(frame.parent_interp, w_value)
        return self.enter_handler(space, bytecode, frame, block, unroller)


class Return(Exception):
    _immutable_fields_ = ["w_value"]

    def __init__(self, w_value):
        self.w_value = w_value


class RaiseFlow(Exception):
    def __init__(self, parent_interp, w_value):
        self.parent_interp = parent_interp
        self.w_value = w_value


class RaiseReturn(RaiseFlow):
    pass


class RaiseBreak(RaiseFlow):
    pass


class Throw(RaiseFlow):
    def __init__(self, name, w_value):
        self.name = name
        self.w_value = w_value


class SuspendedUnroller(W_Root):
    pass


class ApplicationException(SuspendedUnroller):
    kind = 1 << 1

    def __init__(self, e):
        self.e = e

    def nomoreblocks(self):
        raise self.e


class ReturnValue(SuspendedUnroller):
    kind = 1 << 2

    def __init__(self, w_returnvalue):
        self.w_returnvalue = w_returnvalue

    def nomoreblocks(self):
        raise Return(self.w_returnvalue)


class RaiseReturnValue(SuspendedUnroller):
    kind = 1 << 2

    def __init__(self, parent_interp, w_returnvalue):
        self.parent_interp = parent_interp
        self.w_returnvalue = w_returnvalue

    def nomoreblocks(self):
        raise RaiseReturn(self.parent_interp, self.w_returnvalue)


class ContinueLoop(SuspendedUnroller):
    kind = 1 << 3

    def __init__(self, target_pc):
        self.target_pc = target_pc


class BreakLoop(SuspendedUnroller):
    kind = 1 << 4

    def __init__(self, w_value):
        self.w_value = w_value


class RaiseBreakValue(SuspendedUnroller):
    kind = 1 << 5

    def __init__(self, parent_interp, w_value):
        self.parent_interp = parent_interp
        self.w_value = w_value

    def nomoreblocks(self):
        raise RaiseBreak(self.parent_interp, self.w_value)


class ThrowValue(SuspendedUnroller):
    kind = 1 << 6

    def __init__(self, name, w_value):
        self.name = name
        self.w_value = w_value

    def nomoreblocks(self):
        raise Throw(self.name, self.w_value)
