from topaz import consts
from topaz.objects.codeobject import W_CodeObject, UnwindHandler, UnwindInterval


class BaseSymbolTable(object):
    FREEVAR = 0
    CELLVAR = 1

    NORMAL_ARG = 0
    SPLAT_ARG = 1
    KW_ARG = 2            # **rest
    BLOCK_ARG = 3
    KEYWORD_ARG = 4       # a named keyword, `k:` or `k: default`

    def __init__(self, parent_symtable=None):
        self.parent_symtable = parent_symtable
        self.subscopes = {}
        self.cells = {}
        self.arguments = []

        self.cell_numbers = {}

    def add_subscope(self, node, symtable):
        self.subscopes[node] = symtable

    def get_subscope(self, node):
        return self.subscopes[node]

    def declare_argument(self, name, tp=NORMAL_ARG):
        self.arguments.append((name, tp))
        self.declare_local(name)

    def declare_local(self, name):
        self.cells[name] = self.CELLVAR

    def is_defined(self, name):
        return name in self.cells

    def get_cell_num(self, name):
        if name not in self.cell_numbers:
            self.cell_numbers[name] = len(self.cell_numbers)
        return self.cell_numbers[name]


class SymbolTable(BaseSymbolTable):
    def declare_write(self, name):
        if not self.is_defined(name):
            self.declare_local(name)

    def declare_read(self, name):
        pass

    def upgrade_to_closure(self, name):
        pass


class BlockSymbolTable(BaseSymbolTable):
    def declare_read(self, name):
        if name not in self.cells and self.parent_symtable.is_defined(name):
            self.cells[name] = self.FREEVAR
            self.parent_symtable.upgrade_to_closure(name)

    def declare_write(self, name):
        if name not in self.cells:
            if self.parent_symtable.is_defined(name):
                self.cells[name] = self.FREEVAR
                self.parent_symtable.upgrade_to_closure(name)
            else:
                self.declare_local(name)

    def is_defined(self, name):
        return BaseSymbolTable.is_defined(self, name) or self.parent_symtable.is_defined(name)

    def upgrade_to_closure(self, name):
        if name not in self.cells:
            self.parent_symtable.upgrade_to_closure(name)
            self.cells[name] = self.FREEVAR


class SharedScopeSymbolTable(BlockSymbolTable):
    def declare_write(self, name):
        self.parent_symtable.declare_write(name)
        BlockSymbolTable.declare_write(self, name)


class CompilerContext(object):
    F_BLOCK_LOOP = 0
    F_BLOCK_FINALLY = 1
    F_BLOCK_FINALLY_END = 2

    def __init__(self, space, code_name, symtable, filepath):
        self.space = space
        self.code_name = code_name
        self.symtable = symtable
        self.filepath = filepath
        self.consts = []
        self.const_positions = {}
        self.current_lineno = -1
        self.last_lineno = -1

        self.current_block = self.first_block = self.new_block()
        self.frame_blocks = []
        # For `retry`: (block to jump to, len(frame_blocks), except_depth)
        # for each rescue clause being compiled.
        self.retry_targets = []
        # For `redo`: (block to jump to, len(frame_blocks), except_depth)
        self.redo_targets = []
        # How many begin/rescue bodies are being compiled.
        self.except_depth = 0
        # Hidden locals holding the value of $! from before each rescue
        # clause being compiled, outermost first (see TryExcept).
        self.errinfo_stack = []
        # The prologue blocks computing each optional argument's default,
        # then the block after them (see AbstractCallable.compile_bytecode).
        self.default_entry_blocks = []

    def create_bytecode(self, lineno=-1, args=None, defaults=None,
                        first_default_arg=None, splat_arg=None, kwargs=None,
                        kw_defaults=None, kwrest_arg=None, block_arg=None):
        if args is None:
            args = []
        if defaults is None:
            defaults = []
        if kwargs is None:
            kwargs = []
        if kw_defaults is None:
            kw_defaults = []

        cellvars = []
        freevars = []

        # Make sure that any cell vars have a number.
        for name in self.symtable.cells:
            if name not in self.symtable.cell_numbers:
                self.symtable.get_cell_num(name)

        cells = [None] * len(self.symtable.cell_numbers)
        for name, pos in self.symtable.cell_numbers.iteritems():
            cells[pos] = name

        for name in cells:
            kind = self.symtable.cells[name]
            if kind == self.symtable.CELLVAR:
                cellvars.append(name)
            elif kind == self.symtable.FREEVAR:
                freevars.append(name)
            else:
                assert False

        blocks = self.first_block.post_order()
        depth, handlers = self.analyze_unwind(blocks)
        self.lower_unwind(blocks)
        code, lineno_table = self.get_code_lineno_table(blocks)
        unwind_handlers, intervals = self.build_unwind_tables(blocks, handlers)
        # Where to start when k optional positional arguments were passed.
        default_entry_pcs = [self.block_offsets[b] for b in self.default_entry_blocks]
        return W_CodeObject(
            self.code_name,
            self.filepath,
            lineno,
            code,
            depth,
            self.consts[:],
            args,
            splat_arg,
            kwargs,
            kwrest_arg,
            block_arg,
            defaults,
            first_default_arg,
            kw_defaults,
            cellvars,
            freevars,
            lineno_table,
            default_entry_pcs,
            unwind_handlers,
            intervals,
        )

    def get_code_lineno_table(self, blocks):
        offsets = {}
        code_size = 0
        for block in blocks:
            offsets[block] = code_size
            code = []
            linenos = []
            block.get_code(code, linenos)
            code_size += len(code)
        for block in blocks:
            block.patch_locs(offsets)
        self.block_offsets = offsets

        code = []
        linenos = []
        for block in blocks:
            block.get_code(code, linenos)
        return "".join(code), linenos

    def analyze_unwind(self, blocks):
        """Verify every reachable edge before assigning byte offsets.

        The state is (relative operand depth, static handler ID). SETUP
        markers supply exceptional edges explicitly; their targets run in
        the parent scope. Synthetic values after terminal transfers are
        unreachable and are removed by lowering.
        """
        handlers = []
        pending = [(self.first_block, 0, -1)]
        for block in self.default_entry_blocks:
            pending.append((block, 0, -1))
        entries = {}
        maximum = 0
        while pending:
            block, depth, head = pending.pop()
            if block in entries:
                if entries[block] != (depth, head):
                    raise CompilerError("inconsistent stack or handler context at join in %s" % self.code_name)
                continue
            entries[block] = (depth, head)
            maximum = max(maximum, depth)
            falls_through = True
            for instr in block.instrs:
                instr.reachable = True
                instr.handler = head
                instr.depth = depth
                op = instr.opcode
                if op in (consts.SETUP_LOOP, consts.SETUP_EXCEPT,
                          consts.SETUP_FINALLY):
                    if op == consts.SETUP_LOOP:
                        kind = UnwindHandler.LOOP
                        payload = 1
                    elif op == consts.SETUP_EXCEPT:
                        kind = UnwindHandler.RESCUE
                        payload = 2
                    else:
                        kind = UnwindHandler.ENSURE
                        payload = 3
                    handler = CompilerHandler(kind, instr.jump, head, depth)
                    pending.append((instr.jump, depth + payload, head))
                    head = len(handlers)
                    handlers.append(handler)
                elif op == consts.POP_BLOCK:
                    if head < 0:
                        raise CompilerError("scope exit without a handler")
                    handler = handlers[head]
                    retained = handler.stackdepth
                    if handler.kind != UnwindHandler.LOOP:
                        retained += 1
                    depth = min(depth, retained)
                    instr.cleanup_depth = depth
                    instr.push_nil = handler.kind == UnwindHandler.ENSURE
                    if instr.push_nil:
                        depth += 1
                    head = handler.parent
                else:
                    if op == consts.END_RESCUE:
                        depth -= 2
                    else:
                        effect = self._instr_stack_effect(instr)
                        if depth < self._instr_stack_inputs(instr, effect):
                            raise CompilerError("operand stack underflow")
                        depth += effect
                    if depth < 0:
                        raise CompilerError("operand stack underflow")
                    if op == consts.CONTINUE_LOOP:
                        loop = head
                        while loop >= 0 and handlers[loop].kind != UnwindHandler.LOOP:
                            loop = handlers[loop].parent
                        if loop < 0:
                            raise CompilerError("next without a loop")
                        pending.append((instr.jump, handlers[loop].stackdepth, loop))
                    elif instr.has_jump():
                        pending.append((instr.jump, depth, head))
                    if op in (consts.JUMP, consts.RETURN, consts.RAISE_RETURN,
                              consts.BREAK_LOOP, consts.RAISE_BREAK,
                              consts.CONTINUE_LOOP, consts.END_RESCUE):
                        falls_through = False
                        break
                maximum = max(maximum, depth)
            if falls_through and block.next_block is not None:
                pending.append((block.next_block, depth, head))
        self.compiler_handlers = handlers
        return maximum, handlers

    def lower_unwind(self, blocks):
        for block in blocks:
            lowered = []
            for instr in block.instrs:
                if not instr.reachable:
                    continue
                op = instr.opcode
                if op in (consts.SETUP_LOOP, consts.SETUP_EXCEPT,
                          consts.SETUP_FINALLY):
                    # Exceptional reachability was resolved by analysis.
                    continue
                if op == consts.POP_BLOCK:
                    if instr.depth != instr.cleanup_depth:
                        cleanup = Instruction(consts.CLEAR_STACK,
                                              instr.cleanup_depth, -1, instr.lineno)
                        cleanup.handler = instr.handler
                        lowered.append(cleanup)
                    if instr.push_nil:
                        sentinel = Instruction(consts.LOAD_CONST,
                            self.create_const(self.space.w_nil), -1, instr.lineno)
                        # This instruction belongs to the parent scope.
                        sentinel.handler = self._parent_handler(instr.handler)
                        lowered.append(sentinel)
                    continue
                if op in (consts.END_FINALLY, consts.END_RESCUE):
                    instr.opcode = consts.END_FINALLY
                    # Zero encodes the empty chain; other IDs are biased by one.
                    instr.arg0 = instr.handler + 1
                lowered.append(instr)
            block.instrs = lowered

    def _parent_handler(self, head):
        return self.compiler_handlers[head].parent

    def build_unwind_tables(self, blocks, handlers):
        result = []
        for handler in handlers:
            target = self.block_offsets[handler.target]
            if target >= 1 << 16:
                raise CompilerError("code too large to compile (handler target)")
            result.append(UnwindHandler(handler.kind, target, handler.parent,
                                        handler.stackdepth))
        intervals = []
        pc = 0
        start = 0
        previous = -1
        for block in blocks:
            for instr in block.instrs:
                if instr.handler != previous:
                    if previous != -1:
                        intervals.append(UnwindInterval(start, pc, previous))
                    start = pc
                    previous = instr.handler
                pc += 1 + 2 * consts.BYTECODE_NUM_ARGS[instr.opcode]
        if previous != -1:
            intervals.append(UnwindInterval(start, pc, previous))
        return result, intervals

    def _instr_stack_inputs(self, instr, effect):
        op = instr.opcode
        if op in (consts.DUP_TOP, consts.UNPACK_SEQUENCE,
                  consts.UNPACK_SEQUENCE_SPLAT):
            return 1
        if op in (consts.DUP_TWO, consts.ROT_TWO, consts.END_FINALLY):
            return 2
        if op == consts.ROT_THREE:
            return 3
        if op in (consts.JUMP, consts.JUMP_IF_TRUE, consts.JUMP_IF_FALSE,
                  consts.JUMP_IF_KWARG_GIVEN, consts.DISCARD_TOP,
                  consts.RETURN, consts.RAISE_RETURN, consts.RAISE_BREAK,
                  consts.CONTINUE_LOOP, consts.BREAK_LOOP):
            return -effect
        # All other executable instructions produce one value.
        return max(0, 1 - effect)

    def _instr_stack_effect(self, instr):
        stack_effect = consts.BYTECODE_STACK_EFFECT[instr.opcode]
        if stack_effect == consts.SEND_EFFECT:
            stack_effect = -instr.arg1
        elif stack_effect == consts.ARRAY_EFFECT:
            stack_effect = -instr.arg0 + 1
        elif stack_effect == consts.BLOCK_EFFECT:
            stack_effect = -instr.arg0
        elif stack_effect == consts.UNPACK_EFFECT:
            stack_effect = instr.arg0 - 1
        return stack_effect

    def set_lineno(self, lineno):
        return SetLinenoConextManager(self, lineno)

    def enter_frame_block(self, block_type, block):
        return EnterFrameBlockContextManager(self, block_type, block)

    def in_frame_block(self, block_type):
        for t, _ in self.frame_blocks:
            if t == block_type:
                return True
        return False

    def find_frame_block(self, block_type):
        for frame_block in reversed(self.frame_blocks):
            if frame_block[0] == block_type:
                return frame_block[1]
        raise SystemError

    def new_block(self):
        return Block()

    def use_block(self, block):
        self.current_block = block

    def use_next_block(self, block):
        self.current_block.next_block = block
        self.use_block(block)

    def emit(self, opcode, arg0=-1, arg1=-1):
        num_args = 0
        if arg0 != -1:
            num_args += 1
            if arg1 != -1:
                num_args += 1
        if opcode >= 0:
            assert num_args == consts.BYTECODE_NUM_ARGS[opcode]
        instr = Instruction(opcode, arg0, arg1, self.current_lineno)
        self.current_block.instrs.append(instr)
        self.last_lineno = self.current_lineno

    def emit_jump(self, opcode, target, arg1=-1):
        instr = Instruction(opcode, 0, arg1, self.current_lineno)
        instr.jump = target
        self.current_block.instrs.append(instr)

    def get_subctx(self, name, node):
        subscope = self.symtable.get_subscope(node)
        return CompilerContext(self.space, name, subscope, self.filepath)

    def create_const(self, w_obj):
        if w_obj not in self.const_positions:
            self.const_positions[w_obj] = len(self.consts)
            self.consts.append(w_obj)
        return self.const_positions[w_obj]

    def create_int_const(self, intvalue):
        return self.create_const(self.space.newint(intvalue))

    def create_float_const(self, floatvalue):
        return self.create_const(self.space.newfloat(floatvalue))

    def create_symbol_const(self, symbol):
        return self.create_const(self.space.newsymbol(symbol))


class CompilerHandler(object):
    def __init__(self, kind, target, parent, stackdepth):
        self.kind = kind
        self.target = target
        self.parent = parent
        self.stackdepth = stackdepth


class Block(object):
    def __init__(self):
        self.instrs = []
        self.marked = False
        self.next_block = None

    def post_order(self):
        blocks = []
        self._post_order(blocks)
        blocks.reverse()
        return blocks

    def _post_order(self, blocks):
        if self.marked:
            return
        self.marked = True
        if self.next_block is not None:
            self.next_block._post_order(blocks)
        for instr in self.instrs:
            if instr.has_jump():
                instr.jump._post_order(blocks)
        blocks.append(self)

    def patch_locs(self, offsets):
        for instr in self.instrs:
            instr.patch_loc(offsets)

    def get_code(self, code, linenos):
        for instr in self.instrs:
            instr.emit(code, linenos)
        return "".join(code)


class Instruction(object):
    def __init__(self, opcode, arg0, arg1, lineno):
        # Arguments are 16 bits wide.
        if arg0 >= 1 << 16 or arg1 >= 1 << 16:
            raise CompilerError("code too large to compile (an argument above 65535: %d %d %d)" % (opcode, arg0, arg1))
        self.opcode = opcode
        self.arg0 = arg0
        self.arg1 = arg1
        self.lineno = lineno
        self.jump = None
        self.reachable = False
        self.handler = -1
        self.depth = 0
        self.cleanup_depth = 0
        self.push_nil = False

    def emit(self, code, linenos):
        assert self.opcode >= 0
        if self.arg0 >= 1 << 16 or self.arg1 >= 1 << 16:
            raise CompilerError("code too large to compile (operand)")
        code.append(chr(self.opcode))
        linenos.append(self.lineno)
        if self.arg0 != -1:
            code.append(chr(self.arg0 & 0xFF))
            code.append(chr(self.arg0 >> 8))
            linenos.append(self.lineno)
            linenos.append(self.lineno)
        if self.arg1 != -1:
            code.append(chr(self.arg1 & 0xFF))
            code.append(chr(self.arg1 >> 8))
            linenos.append(self.lineno)
            linenos.append(self.lineno)

    def has_jump(self):
        return self.jump is not None

    def patch_loc(self, offsets):
        if self.has_jump():
            target = offsets[self.jump]
            if target >= 1 << 16:
                raise CompilerError("code too large to compile (a jump beyond 65535 bytes)")
            self.arg0 = target


class SetLinenoConextManager(object):
    def __init__(self, ctx, lineno):
        self.ctx = ctx
        self.lineno = lineno

    def __enter__(self):
        self.orig_lineno = self.ctx.current_lineno
        self.ctx.current_lineno = self.lineno

    def __exit__(self, exc_type, exc_value, tb):
        self.ctx.current_lineno = self.orig_lineno


class EnterFrameBlockContextManager(object):
    def __init__(self, ctx, block_type, block):
        self.ctx = ctx
        self.block_type = block_type
        self.block = block

    def __enter__(self):
        self.ctx.frame_blocks.append((self.block_type, self.block))

    def __exit__(self, exc_type, exc_value, tb):
        block_type, block = self.ctx.frame_blocks.pop()
        assert block_type == self.block_type
        assert block is self.block


class CompilerError(Exception):
    def __init__(self, msg=None):
        self.msg = "" if msg is None else msg
