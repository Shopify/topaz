import pytest

from tests.test_unwind import CASES
from .base import BaseJITTest


def ruby_literal(value):
    if value is None:
        return 'nil'
    if isinstance(value, list):
        return '[' + ', '.join(ruby_literal(v) for v in value) + ']'
    return repr(value)


class TestStaticUnwind(BaseJITTest):
    @pytest.mark.parametrize('source, expected', CASES)
    def test_transfers(self, topaz, tmpdir, source, expected):
        self.run(topaz, tmpdir, source + '\nraise "wrong result" unless result == ' + ruby_literal(expected))

    def test_materialized_frame_and_guard_failure(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, '''
          def inner(fail)
            i = 0
            while i < 100
              i += 1
            end
            raise "late exception" if fail
            i
          end
          def outer
            total = 0
            cleaned = 0
            4000.times do |i|
              begin
                total += inner(i == 3999)
              rescue
                total += 7
              ensure
                cleaned += 1
              end
            end
            [total, cleaned]
          end
          raise "bad unwind" unless outer == [399907, 4000]
        ''')
        operations = [op for trace in traces for op in trace.trace.operations]
        assert any(op.name.startswith('call_assembler') for op in operations)
        materialized = False
        for trace in traces:
            ops = trace.trace.operations
            allocated = set(op.res for op in ops if op.name.startswith('new'))
            if any(op.name == 'setfield_gc' and op.args[0] in allocated and
                   'topaz.frame.Frame.inst_bytecode' in str(op) for op in ops):
                materialized = True
        assert materialized
        for op in operations:
            text = str(op)
            assert 'lastblock' not in text
            assert not any(name in text for name in
                           ('FrameBlock', 'LoopBlock', 'ExceptBlock', 'FinallyBlock'))
            if 'call' in op.name:
                assert 'find_handler' not in text
