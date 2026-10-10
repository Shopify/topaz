import pytest

from topaz import consts
from topaz.astcompiler import Block, CompilerContext, Instruction, SymbolTable


def instruction(opcode, arg=-1, target=None, lineno=-1):
    instr = Instruction(opcode, arg, -1, lineno)
    instr.jump = target
    return instr


def block(*instrs):
    result = Block()
    result.instrs = list(instrs)
    return result


@pytest.mark.parametrize('opcode', [consts.JUMP, consts.JUMP_IF_TRUE,
                                  consts.JUMP_IF_FALSE,
                                  consts.JUMP_IF_KWARG_GIVEN])
def test_jump_thread_chain(opcode):
    end = block(instruction(consts.LOAD_SELF), instruction(consts.RETURN))
    middle = block(instruction(consts.JUMP, 0, end))
    empty = block()
    empty.next_block = middle
    start = block(instruction(opcode, 0, empty))
    start.jump_thread()
    assert start.instrs[0].jump is end


def test_jump_to_return():
    end = block(instruction(consts.RETURN))
    start = block(instruction(consts.JUMP, 0, end, lineno=10))
    start.jump_thread()
    instr = start.instrs[0]
    assert instr.opcode == consts.RETURN
    assert instr.jump is None
    assert instr.arg0 == instr.arg1 == -1
    assert instr.lineno == 10


def test_jump_thread_preserves_lines():
    end = block(instruction(consts.LOAD_SELF, lineno=30))
    middle = block(instruction(consts.JUMP, 0, end, lineno=20))
    start = block(instruction(consts.JUMP, 0, middle, lineno=10))
    start.jump_thread()
    assert start.instrs[0].jump is middle
    # Like PyPy, skipping a jump is safe when its destination has its line.
    end.instrs[0].lineno = 20
    start.jump_thread()
    assert start.instrs[0].jump is end


def test_jump_thread_cycles():
    first = block()
    second = block(instruction(consts.JUMP, 0, first))
    first.instrs = [instruction(consts.JUMP, 0, second)]
    first.jump_thread()
    second.jump_thread()
    assert first.instrs[0].opcode == consts.JUMP
    assert second.instrs[0].opcode == consts.JUMP
    empty = block()
    empty.next_block = empty
    start = block(instruction(consts.JUMP, 0, empty))
    start.jump_thread()
    assert start.instrs[0].jump is empty


@pytest.mark.parametrize('opcode', [consts.SETUP_LOOP, consts.SETUP_EXCEPT,
                                  consts.SETUP_FINALLY, consts.CONTINUE_LOOP])
def test_jump_thread_does_not_rewrite_unwind_edges(opcode):
    end = block(instruction(consts.RETURN))
    middle = block(instruction(consts.JUMP, 0, end))
    start = block(instruction(opcode, 0, middle))
    start.jump_thread()
    assert start.instrs[0].jump is middle


def test_jump_thread_stops_at_scope_marker():
    end = block(instruction(consts.POP_BLOCK), instruction(consts.RETURN))
    start = block(instruction(consts.JUMP, 0, end))
    start.jump_thread()
    assert start.instrs[0].jump is end
    assert start.instrs[0].opcode == consts.JUMP


def optimize(first, extra_entries=(), space=None, constants=()):
    ctx = CompilerContext(space, 'test', SymbolTable(), 'test.rb')
    ctx.first_block = first
    ctx.default_entry_blocks = list(extra_entries)
    ctx.consts = list(constants)
    blocks = first.post_order()
    ctx.optimize(blocks)
    return blocks


def test_remove_unreachable_and_jump_to_next():
    end = block(instruction(consts.LOAD_SELF), instruction(consts.RETURN))
    dead = block(instruction(consts.SEND, 0))
    dead.next_block = end
    first = block(instruction(consts.JUMP, 0, end),
                  instruction(consts.LOAD_SELF))
    first.next_block = dead
    blocks = optimize(first)
    assert [i.opcode for b in blocks for i in b.instrs] == [
        consts.LOAD_SELF, consts.RETURN]


def test_remove_unused_constant_across_fallthrough():
    end = block(instruction(consts.DISCARD_TOP),
                instruction(consts.LOAD_SELF), instruction(consts.RETURN))
    first = block(instruction(consts.LOAD_CONST, 0))
    first.next_block = end
    blocks = optimize(first)
    assert [i.opcode for b in blocks for i in b.instrs] == [
        consts.LOAD_SELF, consts.RETURN]


def test_do_not_remove_load_across_multiple_predecessors():
    join = block(instruction(consts.DISCARD_TOP),
                 instruction(consts.LOAD_SELF), instruction(consts.RETURN))
    first = block(instruction(consts.LOAD_SELF),
                  instruction(consts.DUP_TOP),
                  instruction(consts.JUMP_IF_TRUE, 0, join),
                  instruction(consts.DISCARD_TOP),
                  instruction(consts.LOAD_CONST, 0))
    first.next_block = join
    optimize(first)
    assert first.instrs[-1].opcode == consts.LOAD_CONST
    assert join.instrs[0].opcode == consts.DISCARD_TOP


def test_preserve_default_entry():
    body = block(instruction(consts.LOAD_SELF), instruction(consts.RETURN))
    first = block(instruction(consts.LOAD_CONST, 0),
                  instruction(consts.STORE_DEREF, 0),
                  instruction(consts.DISCARD_TOP))
    first.next_block = body
    optimize(first, [first, body])
    assert body.instrs[0].opcode == consts.LOAD_SELF


@pytest.mark.parametrize('marker', [consts.SETUP_LOOP, consts.SETUP_EXCEPT,
                                  consts.SETUP_FINALLY])
def test_preserve_handler_only_entry(marker):
    handler = block(instruction(consts.LOAD_SELF), instruction(consts.RETURN))
    first = block(instruction(marker, 0, handler),
                  instruction(consts.LOAD_SELF), instruction(consts.RETURN))
    optimize(first)
    assert handler.instrs
    assert first.instrs[0].jump is handler


def test_preserve_scope_boundary():
    first = block(instruction(consts.LOAD_CONST, 0),
                  instruction(consts.POP_BLOCK),
                  instruction(consts.DISCARD_TOP),
                  instruction(consts.LOAD_SELF), instruction(consts.RETURN))
    optimize(first)
    assert len(first.instrs) == 5


def test_preserve_distinct_load_line():
    first = block(instruction(consts.LOAD_CONST, 0, lineno=10),
                  instruction(consts.DISCARD_TOP, lineno=10),
                  instruction(consts.LOAD_SELF, lineno=11),
                  instruction(consts.RETURN, lineno=11))
    optimize(first)
    assert first.instrs[0].opcode == consts.LOAD_CONST


@pytest.mark.parametrize('value', ['true', 'false', 'nil', 'zero'])
@pytest.mark.parametrize('opcode', [consts.JUMP_IF_TRUE, consts.JUMP_IF_FALSE])
def test_fold_constant_condition(space, value, opcode):
    values = {'true': space.w_true, 'false': space.w_false,
              'nil': space.w_nil, 'zero': space.newint(0)}
    taken = block(instruction(consts.LOAD_SELF), instruction(consts.RETURN))
    other = block(instruction(consts.LOAD_DEREF, 0), instruction(consts.RETURN))
    first = block(instruction(consts.LOAD_CONST, 0),
                  instruction(opcode, 0, taken))
    first.next_block = other
    blocks = optimize(first, space=space, constants=[values[value]])
    truth = value in ('true', 'zero')
    expected = consts.LOAD_SELF if truth == (opcode == consts.JUMP_IF_TRUE) else consts.LOAD_DEREF
    assert [i.opcode for b in blocks for i in b.instrs] == [expected, consts.RETURN]



def test_unused_constant_across_jump_and_branch_inversion():
    body = block(instruction(consts.DISCARD_TOP),
                 instruction(consts.LOAD_SELF), instruction(consts.RETURN))
    other = block(instruction(consts.LOAD_CONST, 1), instruction(consts.RETURN))
    first = block(instruction(consts.LOAD_DEREF, 0),
                  instruction(consts.JUMP_IF_FALSE, 0, other),
                  instruction(consts.LOAD_CONST, 0),
                  instruction(consts.JUMP, 0, body))
    first.next_block = other
    other.next_block = body
    blocks = optimize(first)
    assert [i.opcode for b in blocks for i in b.instrs] == [
        consts.LOAD_DEREF, consts.JUMP_IF_TRUE,
        consts.LOAD_CONST, consts.RETURN,
        consts.LOAD_SELF, consts.RETURN]
    assert first.instrs[1].jump.instrs[0].opcode == consts.LOAD_SELF


def test_skip_discard_keeps_other_incoming_values():
    join = block(instruction(consts.DISCARD_TOP),
                 instruction(consts.LOAD_SELF), instruction(consts.RETURN))
    first = block(instruction(consts.LOAD_SELF),
                  instruction(consts.DUP_TOP),
                  instruction(consts.JUMP_IF_TRUE, 0, join),
                  instruction(consts.DISCARD_TOP),
                  instruction(consts.LOAD_CONST, 0),
                  instruction(consts.JUMP, 0, join))
    optimize(first)
    # The conditional edge still has a value to discard.
    assert first.instrs[2].jump.instrs[0].opcode == consts.DISCARD_TOP
    assert not any(i.opcode == consts.LOAD_CONST for i in first.instrs)


def test_optimizer_is_idempotent():
    end = block(instruction(consts.LOAD_SELF), instruction(consts.RETURN))
    middle = block(instruction(consts.JUMP, 0, end))
    first = block(instruction(consts.JUMP, 0, middle))
    ctx = CompilerContext(None, 'test', SymbolTable(), 'test.rb')
    ctx.first_block = first
    blocks = first.post_order()
    assert ctx.optimize(blocks)
    assert not ctx.optimize(blocks)


def compiled_instructions(code):
    result = []
    pc = 0
    while pc < len(code.code):
        opcode = ord(code.code[pc])
        args = []
        for i in range(consts.BYTECODE_NUM_ARGS[opcode]):
            offset = pc + 1 + 2 * i
            args.append(ord(code.code[offset]) | ord(code.code[offset + 1]) << 8)
        result.append((pc, opcode, args))
        pc += 1 + 2 * len(args)
    return result


def method_code(space, source):
    from topaz.objects.codeobject import W_CodeObject
    code = space.compile(source, 'optimizer.rb')
    return [c for c in code.consts_w if isinstance(c, W_CodeObject)][0]


def test_compile_guard(space):
    code = method_code(space, 'def f(block); return 7 unless block; 42; end')
    instrs = compiled_instructions(code)
    assert [op for pc, op, args in instrs] == [
        consts.LOAD_DEREF, consts.JUMP_IF_TRUE,
        consts.LOAD_CONST, consts.RETURN,
        consts.LOAD_CONST, consts.RETURN]
    assert code.max_stackdepth == 1
    assert len(code.code) == len(code.lineno_table)
    assert space.int_w(space.execute('def f(block); return 7 unless block; 42; end; f(false)')) == 7
    assert space.int_w(space.execute('f(true)')) == 42


def test_compile_nested_jump_threading(space):
    code = method_code(space, '''def f(a, b)
      c = if a
        if b; 1; else; 2; end
      else
        3
      end
      c
    end''')
    instrs = compiled_instructions(code)
    by_pc = dict((pc, op) for pc, op, args in instrs)
    assert any(op == consts.JUMP for pc, op, args in instrs)
    for pc, op, args in instrs:
        if op == consts.JUMP:
            assert by_pc[args[0]] != consts.JUMP


def test_compile_constant_loop_with_ensure_and_break(space):
    source = '''def f(log)
      while true
        begin
          break 42
        ensure
          log << 7
        end
      end
    end'''
    code = method_code(space, source)
    assert consts.JUMP_IF_FALSE not in [op for pc, op, args in compiled_instructions(code)]
    result = space.execute(source + '; log = []; [f(log), log]')
    values = space.listview(result)
    assert space.int_w(values[0]) == 42
    assert [space.int_w(v) for v in space.listview(values[1])] == [7]


def test_compile_default_entries_and_rescue(space):
    source = '''def f(a = (raise("a") rescue 3), b = (raise("b") rescue 4), c: 5)
      return [a, b, c] if a
      nil
    end'''
    code = method_code(space, source)
    starts = [pc for pc, op, args in compiled_instructions(code)]
    assert all(pc in starts for pc in code.default_entry_pcs)
    assert all(h.target_pc in starts for h in code.unwind_handlers)
    result = space.execute(source + '; [f, f(8), f(8, 9, c: 10)]')
    assert [[space.int_w(v) for v in space.listview(row)]
            for row in space.listview(result)] == [[3, 4, 5], [8, 4, 5], [8, 9, 10]]


def test_compile_empty_infinite_loop(space):
    code = method_code(space, 'def f; while true; end; end')
    instrs = compiled_instructions(code)
    assert instrs[0] == (0, consts.JUMP, [0])
    # Keep the unwind-only loop exit even though there is no normal exit.
    assert code.unwind_handlers[0].target_pc in [pc for pc, op, args in instrs]


def test_compile_keeps_distinct_source_lines(space):
    # Bare literal nodes currently carry no source line; sends do.
    code = method_code(space, 'def f\n  1.to_s\n  2.to_s\n  3.to_s\nend')
    assert set([2, 3, 4]).issubset(set(code.lineno_table))


def test_jump_to_return_on_another_line_is_not_inlined():
    end = block(instruction(consts.RETURN, lineno=20))
    first = block(instruction(consts.JUMP, 0, end, lineno=10))
    first.jump_thread()
    assert first.instrs[0].opcode == consts.JUMP
    assert first.instrs[0].jump is end


@pytest.mark.parametrize('opcode', [consts.JUMP_IF_TRUE, consts.JUMP_IF_FALSE])
def test_thread_repeated_boolean_test(opcode):
    end = block(instruction(consts.RETURN))
    middle = block(instruction(consts.DUP_TOP), instruction(opcode, 0, end))
    first = block(instruction(consts.DUP_TOP), instruction(opcode, 0, middle))
    assert first.jump_thread()
    assert first.instrs[1].jump is end
    # Other predecessors still need to test the value at the original target.
    assert [i.opcode for i in middle.instrs] == [consts.DUP_TOP, opcode]


@pytest.mark.parametrize('barrier', ['no_dup', 'opposite', 'dup_line', 'branch_line'])
def test_repeated_boolean_test_barriers(barrier):
    end = block(instruction(consts.RETURN))
    middle = block(instruction(consts.DUP_TOP),
                   instruction(consts.JUMP_IF_TRUE, 0, end))
    first = block(instruction(consts.DUP_TOP, lineno=10),
                  instruction(consts.JUMP_IF_TRUE, 0, middle, lineno=10))
    if barrier == 'no_dup':
        first.instrs.pop(0)
    elif barrier == 'opposite':
        middle.instrs[1].opcode = consts.JUMP_IF_FALSE
    elif barrier == 'dup_line':
        middle.instrs[0].lineno = 20
    else:
        middle.instrs[1].lineno = 20
    first.jump_thread()
    assert first.instrs[-1].jump is middle


def test_repeated_boolean_test_cycle():
    first = block(instruction(consts.DUP_TOP))
    second = block(instruction(consts.DUP_TOP),
                   instruction(consts.JUMP_IF_FALSE, 0, first))
    first.instrs.append(instruction(consts.JUMP_IF_FALSE, 0, second))
    first.jump_thread()
    second.jump_thread()
    assert first.instrs[1].jump in (first, second)
    assert second.instrs[1].jump in (first, second)


@pytest.mark.parametrize('operator', ['&&', '||'])
def test_compile_boolean_chain(space, operator):
    # The shape used by Comparable#clamp and Encoding.find.
    source = 'def f(a, b, c); a %s b %s c; end' % (operator, operator)
    code = method_code(space, source)
    instrs = compiled_instructions(code)
    by_pc = dict((pc, op) for pc, op, args in instrs)
    branches = [(op, args) for pc, op, args in instrs
                if op in (consts.JUMP_IF_TRUE, consts.JUMP_IF_FALSE)]
    assert len(branches) == 2
    assert all(by_pc[args[0]] != consts.DUP_TOP for op, args in branches)
    space.execute(source)
    for a in ['nil', 'false', '0']:
        for b in ['nil', 'false', '1']:
            result = space.execute('f(%s, %s, 2)' % (a, b))
            if operator == '&&':
                expected = a if a != '0' else b if b != '1' else '2'
            else:
                expected = a if a == '0' else b if b == '1' else '2'
            assert space.is_true(space.send(
                result, 'equal?', [space.execute(expected)]))
    # A skipped operand must not be evaluated.
    if operator == '&&':
        expression = 'false && raise("bad") && raise("bad")'
    else:
        expression = 'true || raise("bad") || raise("bad")'
    space.execute(expression)


@pytest.mark.parametrize('producer', [consts.BUILD_ARRAY, consts.BUILD_ARRAY_SPLAT])
@pytest.mark.parametrize('duplicate', [False, True])
@pytest.mark.parametrize('nil_is_empty', [0, 1])
def test_remove_known_array_coercion(producer, duplicate, nil_is_empty):
    instrs = [instruction(producer, 2)]
    if duplicate:
        instrs.append(instruction(consts.DUP_TOP))
    instrs.extend([instruction(consts.COERCE_ARRAY, nil_is_empty),
                   instruction(consts.RETURN)])
    first = block(*instrs)
    optimize(first)
    assert consts.COERCE_ARRAY not in [i.opcode for i in first.instrs]
    assert first.instrs[0].opcode == producer
    assert (consts.DUP_TOP in [i.opcode for i in first.instrs]) == duplicate


@pytest.mark.parametrize('barrier', ['unknown_value', 'scope', 'line'])
def test_known_array_coercion_barriers(barrier):
    instrs = [instruction(consts.BUILD_ARRAY, 0)]
    if barrier == 'unknown_value':
        instrs.append(instruction(consts.LOAD_DEREF, 0))
    elif barrier == 'scope':
        instrs.append(instruction(consts.POP_BLOCK))
    instrs.extend([instruction(consts.COERCE_ARRAY, 0,
                              lineno=20 if barrier == 'line' else -1),
                   instruction(consts.RETURN, lineno=30)])
    first = block(*instrs)
    optimize(first)
    assert consts.COERCE_ARRAY in [i.opcode for i in first.instrs]


def test_compile_array_swap(space):
    # Array#shuffle! uses this indexed multiple-assignment shape.
    source = 'def f(a, i, j); a[i], a[j] = a[j], a[i]; end'
    code = method_code(space, source)
    ops = [op for pc, op, args in compiled_instructions(code)]
    assert consts.COERCE_ARRAY not in ops
    assert any(ops[i:i + 3] == [consts.BUILD_ARRAY, consts.DUP_TOP,
                              consts.UNPACK_SEQUENCE]
               for i in range(len(ops) - 2))
    result = space.execute(source + '; a = [1, 2]; value = f(a, 0, 1); [a, value]')
    assert [[space.int_w(v) for v in space.listview(row)]
            for row in space.listview(result)] == [[2, 1], [2, 1]]


def test_compile_multiple_assignment_keeps_coercion(space):
    source = 'def f(value); a, b = value; [a, b]; end'
    code = method_code(space, source)
    ops = [op for pc, op, args in compiled_instructions(code)]
    assert consts.COERCE_ARRAY in ops
    result = space.execute(source + '''
      class OptimizerArrayCoercion
        def to_ary; [3, 4]; end
      end
      f(OptimizerArrayCoercion.new)
    ''')
    assert [space.int_w(v) for v in space.listview(result)] == [3, 4]
