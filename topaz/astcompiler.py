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
        if self.optimize(blocks):
            # Validate the input graph before optimization (including dead
            # constant branches), then recompute exact depths and handler IDs
            # for the simplified graph. Scope markers have not been lowered.
            for block in blocks:
                for instr in block.instrs:
                    instr.reachable = False
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

    def optimize(self, blocks):
        """Simplify the CFG before lowering scope markers or assigning PCs.

        As in PyPy's assembler, keep the original layout and empty dead blocks
        instead of reordering the graph. Default-argument entries are additional
        roots; SETUP markers keep unwind-only destinations reachable.
        """
        any_changed = False
        changed = True
        while changed:
            changed = False
            for block in blocks:
                if block.jump_thread():
                    changed = True
                if self.optimize_local(block):
                    changed = True
            if self.skip_unused_constants(blocks):
                changed = True
            predecessors, removed = self.remove_unreachable(blocks)
            changed = changed or removed
            for block in blocks:
                # Only merge a fallthrough with no other entry. In particular,
                # never pull a default prologue or handler into its predecessor.
                target = block.next_block
                if (target is not None and target is not block and
                        predecessors.get(target, 0) == 1):
                    block.instrs.extend(target.instrs)
                    block.next_block = target.next_block
                    target.instrs = []
                    target.next_block = None
                    changed = True
            # A jump to the next emitted block can fall through instead.
            following = None
            for index in range(len(blocks) - 1, -1, -1):
                block = blocks[index]
                if not block.instrs:
                    continue
                last = block.instrs[-1]
                # if L1; jump L2; L1: ... -> unless L2; L1: ...
                if last.opcode == consts.JUMP and len(block.instrs) >= 2:
                    branch = block.instrs[-2]
                    if (following is not None and
                            branch.opcode in (consts.JUMP_IF_TRUE, consts.JUMP_IF_FALSE)
                            and branch.jump is following and
                            (last.lineno == -1 or last.lineno == branch.lineno)):
                        if branch.opcode == consts.JUMP_IF_TRUE:
                            branch.opcode = consts.JUMP_IF_FALSE
                        else:
                            branch.opcode = consts.JUMP_IF_TRUE
                        branch.jump = last.jump
                        block.instrs.pop()
                        block.next_block = following
                        last = branch
                        changed = True
                if (following is not None and last.opcode == consts.JUMP and
                        last.jump is following and
                        (last.lineno == -1 or
                         last.lineno == following.instrs[0].lineno)):
                    block.instrs.pop()
                    block.next_block = following
                    changed = True
                if block.instrs:
                    following = block
            any_changed = any_changed or changed
        return any_changed

    def skip_unused_constants(self, blocks):
        # A statement-valued branch often ends with LOAD_CONST nil; JUMP to
        # a shared DISCARD_TOP. Split the join so just this edge can bypass
        # the discard; other incoming edges (including handlers/defaults)
        # must still pop their value. Scope markers remain barriers.
        changed = False
        index = 0
        while index < len(blocks):
            block = blocks[index]
            index += 1
            if len(block.instrs) < 2:
                continue
            load = block.instrs[-2]
            jump = block.instrs[-1]
            if (load.opcode != consts.LOAD_CONST or jump.opcode != consts.JUMP
                    or load.lineno != -1):
                continue
            target = jump.jump
            if (not target.instrs or target.instrs[0].opcode != consts.DISCARD_TOP
                    or target.instrs[0].lineno != -1):
                continue
            rest = Block()
            rest.instrs = target.instrs[1:]
            rest.next_block = target.next_block
            target.instrs = target.instrs[:1]
            target.next_block = rest
            blocks.insert(blocks.index(target) + 1, rest)
            del block.instrs[-2]
            jump.jump = rest
            changed = True
        return changed

    def remove_unreachable(self, blocks):
        predecessors = {self.first_block: 1}
        pending = [self.first_block]
        for block in self.default_entry_blocks:
            predecessors[block] = predecessors.get(block, 0) + 1
            pending.append(block)
        seen = {}
        changed = False
        while pending:
            block = pending.pop()
            if block in seen:
                continue
            seen[block] = True
            for index, instr in enumerate(block.instrs):
                if instr.jump is not None:
                    target = instr.jump
                    predecessors[target] = predecessors.get(target, 0) + 1
                    pending.append(target)
                if instr.is_terminal():
                    if index + 1 < len(block.instrs):
                        del block.instrs[index + 1:]
                        changed = True
                    if block.next_block is not None:
                        block.next_block = None
                        changed = True
                    break
            if block.next_block is not None:
                target = block.next_block
                predecessors[target] = predecessors.get(target, 0) + 1
                pending.append(target)
        for block in blocks:
            if block not in seen:
                if block.instrs or block.next_block is not None:
                    block.instrs = []
                    block.next_block = None
                    changed = True
        return predecessors, changed

    def optimize_local(self, block):
        changed = False
        instrs = block.instrs
        index = 0
        while index + 1 < len(instrs):
            load = instrs[index]
            following = instrs[index + 1]
            if load.opcode in (consts.BUILD_ARRAY, consts.BUILD_ARRAY_SPLAT):
                # Multiple assignment retains the original RHS with DUP_TOP
                # before coercing the copy. Both are already known arrays.
                coerce_index = index + 1
                if following.opcode == consts.DUP_TOP:
                    coerce_index += 1
                if (coerce_index < len(instrs) and
                        instrs[coerce_index].opcode == consts.COERCE_ARRAY and
                        self.can_remove(instrs, coerce_index, 1)):
                    del instrs[coerce_index]
                    changed = True
                    continue
            if load.opcode == consts.LOAD_CONST:
                if (following.opcode == consts.DISCARD_TOP and
                        self.can_remove(instrs, index, 2)):
                    del instrs[index:index + 2]
                    changed = True
                    continue
                if following.opcode in (consts.JUMP_IF_TRUE, consts.JUMP_IF_FALSE):
                    taken = self.space.is_true(self.consts[load.arg0])
                    if following.opcode == consts.JUMP_IF_FALSE:
                        taken = not taken
                    if taken and (load.lineno == -1 or load.lineno == following.lineno):
                        following.opcode = consts.JUMP
                        del instrs[index]
                        changed = True
                        continue
                    if not taken and self.can_remove(instrs, index, 2):
                        del instrs[index:index + 2]
                        changed = True
                        continue
            index += 1
        return changed

    @staticmethod
    def can_remove(instrs, start, count):
        # Don't erase an independently observable source line. Synthetic
        # instructions have no line; a real line must survive on the next op.
        following_line = -1
        if start + count < len(instrs):
            following_line = instrs[start + count].lineno
        for index in range(start, start + count):
            line = instrs[index].lineno
            if line != -1 and line != following_line:
                return False
        return True

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

    def jump_thread(self):
        """Thread ordinary branches, retaining source lines like PyPy's assembler.

        Scope markers and unwind transfers are deliberately not threaded: their
        destinations describe handler entry states, not ordinary branch edges.
        """
        changed = False
        for index, instr in enumerate(self.instrs):
            if instr.opcode not in (consts.JUMP, consts.JUMP_IF_TRUE,
                                    consts.JUMP_IF_FALSE,
                                    consts.JUMP_IF_KWARG_GIVEN):
                continue
            seen = {}
            target = instr.jump
            while target is not None and target not in seen:
                seen[target] = True
                if not target.instrs:
                    if target.next_block is None:
                        break
                    target = target.next_block
                    continue
                dest = target.instrs[0]
                if dest is instr:
                    break
                same_target_line = (
                    dest.opcode == consts.JUMP and len(dest.jump.instrs) > 0 and
                    dest.jump.instrs[0].lineno == dest.lineno)
                if (dest.lineno != -1 and dest.lineno != instr.lineno and
                        not same_target_line):
                    break
                if dest.opcode == consts.JUMP:
                    target = dest.jump
                elif (instr.opcode in (consts.JUMP_IF_TRUE, consts.JUMP_IF_FALSE)
                      and index > 0 and self.instrs[index - 1].opcode == consts.DUP_TOP
                      and dest.opcode == consts.DUP_TOP and len(target.instrs) > 1
                      and target.instrs[1].opcode == instr.opcode
                      and (target.instrs[1].lineno == -1 or
                           target.instrs[1].lineno == instr.lineno)):
                    # The taken edge retains the tested value. Testing a copy
                    # of it again has the same outcome and no net stack effect.
                    target = target.instrs[1].jump
                elif (instr.opcode == consts.JUMP and
                      dest.opcode == consts.RETURN):
                    instr.opcode = consts.RETURN
                    instr.arg0 = instr.arg1 = -1
                    target = None
                    changed = True
                    break
                else:
                    break
            if instr.jump is not target:
                instr.jump = target
                changed = True
        return changed

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

    def is_terminal(self):
        return self.opcode in (consts.JUMP, consts.RETURN, consts.RAISE_RETURN,
                              consts.BREAK_LOOP, consts.RAISE_BREAK,
                              consts.CONTINUE_LOOP, consts.END_RESCUE)

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
