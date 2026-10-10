"""Static unwind metadata and transfers with live operand-stack values."""
import copy

import pytest

from topaz import consts
from topaz.astcompiler import CompilerContext, CompilerError, SymbolTable
from topaz.interpreter import Interpreter
from topaz.objects.codeobject import UnwindHandler, W_CodeObject
from .base import BaseTopazTest


def instructions(code):
    pc = 0
    while pc < len(code.code):
        op = ord(code.code[pc])
        yield pc, op
        pc += 1 + 2 * consts.BYTECODE_NUM_ARGS[op]


def test_interval_boundaries_and_copy(space):
    code = space.compile('begin; 1; rescue; 2; ensure; 3; end', None)
    assert code.unwind_handlers
    for entry in code.unwind_intervals:
        assert entry.start < entry.end
        assert code.handler_at(entry.start) == entry.handler
        assert code.handler_at(entry.end - 1) == entry.handler
        assert code.handler_at(entry.end) != entry.handler
    for pc in range(len(code.code) + 1):
        matches = [i.handler for i in code.unwind_intervals if i.start <= pc < i.end]
        assert code.handler_at(pc) == (matches[0] if matches else -1)
    cloned = copy.deepcopy(code)
    assert cloned.unwind_handlers is code.unwind_handlers
    assert cloned.unwind_intervals is code.unwind_intervals
    assert not hasattr(space.create_frame(code), 'lastblock')
    assert not any(name.startswith('SETUP_') or name == 'POP_BLOCK'
                   for name in consts.BYTECODE_NAMES)


def test_nested_handlers_and_disjoint_ranges(space):
    code = space.compile('begin; 1; begin; 2; rescue; 3; end; 4; ensure; 5; end', None)
    outer, inner = code.unwind_handlers
    assert outer.kind == UnwindHandler.ENSURE
    assert outer.parent == -1
    assert inner.kind == UnwindHandler.RESCUE
    assert inner.parent == 0
    assert outer.stackdepth == inner.stackdepth == 0
    assert len([i for i in code.unwind_intervals if i.handler == 0]) >= 2
    assert code.handler_at(outer.target_pc) == -1
    assert code.handler_at(inner.target_pc) == 0
    for pc, op in instructions(code):
        if op == consts.END_FINALLY:
            resume = ord(code.code[pc + 1]) + 256 * ord(code.code[pc + 2]) - 1
            assert resume == code.handler_at(pc)


def test_optional_default_entry_handlers(space):
    code = space.compile('def f(a = (1 rescue 2), b = (3 rescue 4)); a + b; end', None)
    method = [c for c in code.consts_w if isinstance(c, W_CodeObject)][0]
    assert len(method.default_entry_pcs) == 3
    first, second, body = method.default_entry_pcs
    assert first < second < body
    # The hidden $! save precedes entry into each rescue scope.
    assert [method.handler_at(pc) for pc in (first, second, body)] == [-1, -1, -1]
    assert len(method.unwind_handlers) == 2


@pytest.mark.parametrize('handler_mismatch', [False, True])
def test_reject_inconsistent_join(space, handler_mismatch):
    ctx = CompilerContext(space, 'invalid', SymbolTable(), 'invalid.rb')
    other, join, handler = ctx.new_block(), ctx.new_block(), ctx.new_block()
    ctx.emit(consts.LOAD_CONST, ctx.create_const(space.w_nil))
    ctx.emit_jump(consts.JUMP_IF_TRUE, other)
    if handler_mismatch:
        ctx.emit_jump(consts.SETUP_EXCEPT, handler)
    else:
        ctx.emit(consts.LOAD_CONST, 0)
    ctx.emit_jump(consts.JUMP, join)
    ctx.use_next_block(other)
    ctx.emit_jump(consts.JUMP, join)
    ctx.use_next_block(join)
    ctx.emit(consts.LOAD_CONST, 0)
    ctx.emit(consts.RETURN)
    ctx.use_next_block(handler)
    ctx.emit(consts.END_RESCUE)
    with pytest.raises(CompilerError):
        ctx.create_bytecode()


def test_cleanup_clears_abandoned_pending_transfer(space):
    code = space.compile('begin; return Object.new; ensure; return 42; end', None)
    frame = space.create_frame(code)
    with space.getexecutioncontext().visit_frame(frame):
        assert space.int_w(space.execute_frame(frame, code)) == 42
    base = len(code.cellvars)
    assert frame.stackpos == base
    assert all(w is None for w in frame.localsstack_w[base:base + code.max_stackdepth])


def test_cleanup_never_increases_stack(space):
    frame = space.create_frame(space.compile('nil', None))
    base = frame.stackpos
    Interpreter().clear_stack(frame, 100)
    assert frame.stackpos == base


@pytest.mark.parametrize('opcode, arg', [
    (consts.DUP_TOP, -1), (consts.ROT_TWO, -1),
    (consts.UNPACK_SEQUENCE, 2), (consts.STORE_DEREF, 0)])
def test_reject_missing_operands(space, opcode, arg):
    ctx = CompilerContext(space, 'invalid', SymbolTable(), 'invalid.rb')
    ctx.emit(opcode, arg)
    with pytest.raises(CompilerError):
        ctx.create_bytecode()


def test_handler_only_reachable_by_unwind(space):
    code = space.compile('begin; return 1; ensure; 2.to_s; end', None)
    handler = code.unwind_handlers[0]
    starts = [pc for pc, op in instructions(code)]
    assert handler.target_pc in starts
    assert len(code.lineno_table) == len(code.code)
    assert code.handler_at(handler.target_pc) == -1


def test_metadata_display(space):
    from tests.test_compiler import TestCompiler
    code = space.compile('while false; nil; end', None)
    lines = TestCompiler().get_lines(code, include_unwind=True)
    assert any(line.startswith('HANDLER 0 kind=0') for line in lines)
    assert any(line.startswith('UNWIND [0, ') for line in lines)


# These cases also run on CRuby and the translated binary (see JIT tests).
CASES = [
    ('''
      def f(log)
        begin
          begin
            return 11
          ensure
            log << 1
            begin
              raise "inner"
            rescue
              log << 2
            ensure
              log << 3
            end
          end
        ensure
          log << 4
        end
      end
      log = []; result = [f(log), log]
    ''', [11, [1, 2, 3, 4]]),
    ('''
      def f
        begin
          return 11
        ensure
          begin
            return 22
          ensure
            return 33
          end
        end
      end
      result = f
    ''', 33),
    ('''
      def f
        begin
          raise "old"
        ensure
          raise "new"
        end
      end
      begin; f; rescue => e; result = [e.message, $!.message]; end
      result << $!
    ''', ['new', 'new', None]),
    ('''
      result = [1, (begin
        [2, 3, Integer("bad")]
      rescue ArgumentError
        4
      ensure
        [5, 6]
      end), 7]
    ''', [1, 4, 7]),
    ('''
      log = []; i = 0
      value = while i < 5
        i += 1
        begin
          next if i < 3
          break 19
        ensure
          log << i
        end
      end
      result = [value, log]
    ''', [19, [1, 2, 3]]),
    ('''
      i = 0; log = []
      begin
        i += 1
        redo if i == 1
        begin; next; ensure; log << i; end
      end while i < 3
      result = log
    ''', [2, 3]),
    ('''
      n = 0
      begin
        n += 1
        raise "again" if n < 3
      rescue
        while true
          begin
            retry
          rescue
            raise "wrong"
          end
        end
      end
      result = [n, $!]
    ''', [3, None]),
    ('''
      def matcher
        raise "matching"
      end
      begin
        begin
          raise "body"
        rescue matcher
          result = "wrong"
        end
      rescue => e
        result = e.message
      end
    ''', 'matching'),
    ('''
      begin
        begin
          1
        rescue
          result = "wrong"
        else
          raise "else"
        end
      rescue => e
        result = e.message
      end
    ''', 'else'),
    ('''
      def f(a = (raise("default") rescue 4), b = (begin; 5; ensure; 6; end))
        [a, b]
      end
      result = [f, f(7), f(7, 8)]
    ''', [[4, 5], [7, 5], [7, 8]]),
    ('''
      log = []
      result = catch(:tag) do
        begin
          begin
            throw :tag, 42
          ensure
            log << 1
          end
        ensure
          log << 2
        end
      end
      result = [result, log]
    ''', [42, [1, 2]]),
    ('''
      def f(log)
        [1].each do
          begin
            return 12
          ensure
            log << 1
          end
        end
      end
      log = []
      value = [1].each do
        begin; break 13; ensure; log << 2; end
      end
      result = [f(log), value, log]
    ''', [12, 13, [2, 1]]),
    ('''
      f = Fiber.new do
        begin
          raise "pending"
        ensure
          Fiber.yield 1
          begin; Fiber.yield 2; ensure; Fiber.yield 3; end
        end
      end
      log = [f.resume, f.resume, f.resume]
      begin; f.resume; rescue => e; log << e.message; end
      result = log
    ''', [1, 2, 3, 'pending']),
    ('''
      def recurse(n, log)
        begin
          return 9 if n == 0
          recurse(n - 1, log)
        ensure
          log << n
        end
      end
      log = []; result = [recurse(3, log), log]
    ''', [9, [0, 1, 2, 3]]),
    ('''
      log = []
      f = lambda do
        begin; return 8; ensure; log << 1; end
      end
      result = [f.call, log]
    ''', [8, [1]]),
    ('''
      log = []
      begin
        raise "outer"
      rescue
        log << $!.message
        begin
          begin; raise "inner"; rescue; log << $!.message; end
        ensure
          log << $!.message
        end
        log << $!.message
      end
      result = [log, $!]
    ''', [['outer', 'inner', 'outer', 'outer'], None]),
    ('''
      def f
        while true
          begin; return 1; ensure; break 2; end
        end
      end
      result = f
    ''', 2),
    ('''
      i = 0
      while i < 3
        begin
          raise "superseded"
        ensure
          i += 1
          next
        end
      end
      result = i
    ''', 3),
]


class TestUnwindBehavior(BaseTopazTest):
    @pytest.mark.parametrize('source, expected', CASES)
    def test_transfer(self, space, source, expected):
        assert self.unwrap(space, space.execute(source + '\nreturn result')) == expected

    def test_line_hook_exception_is_rescued(self, space):
        result = space.execute('''
          def traced
            begin
              a = 1.to_s
              a = 2.to_s
            rescue => e
              return e.message
            end
          end
          set_trace_func(proc { |event, file, line, name, binding, klass|
            if event == "line" && line == 5
              set_trace_func(nil)
              raise "trace"
            end
          })
          return traced
        ''')
        assert space.str_w(result) == 'trace'

    @pytest.mark.xfail(reason='pre-existing: ensure replacing an exception does not restore $!')
    def test_replacing_exception_restores_errinfo(self, space):
        result = space.execute('''
          def f
            begin; raise "old"; ensure; return 3; end
          end
          return [f, $! && $!.message]
        ''')
        assert self.unwrap(space, result) == [3, None]


@pytest.mark.parametrize('prefix', ['Object;', 'X = 1;', 'defined?(Object);'])
def test_constant_stack_effect_before_handler(space, prefix):
    code = space.compile(prefix + 'begin; nil; rescue; nil; end', None)
    assert code.unwind_handlers[0].stackdepth == 0


def test_splatted_yield_stack_effect(space):
    code = space.compile('def f; yield(*[1]); begin; yield(*[2]); rescue; nil; end; end', None)
    method = [c for c in code.consts_w if isinstance(c, W_CodeObject)][0]
    assert method.unwind_handlers[0].stackdepth == 0
