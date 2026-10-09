import pytest

from .base import BaseJITTest


class TestHash(BaseJITTest):
    @pytest.mark.parametrize("key, initial, updated", [
        ("keys[1]", 20000, 30000),
        ("keys[i & 1]", 15000, 20000),
    ])
    def test_symbol_lookup(self, topaz, tmpdir, key, initial, updated):
        traces = self.run(topaz, tmpdir, '''
        def lookup(h, keys)
          i = 0
          total = 0
          while i < 10000
            total += h[%s]
            i += 1
          end
          total
        end
        h = {a: 1, b: 2}
        keys = [:a, :b]
        raise 'wrong value' unless lookup(h, keys) == %d
        h[:b] = 3
        raise 'stale value' unless lookup(h, keys) == %d
        ''' % (key, initial, updated))
        loops = [trace.loop for trace in traces
                 if 'in lookup' in trace.trace.comment
                 and 'loop with' in trace.trace.comment]
        assert loops
        for loop in loops:
            # Exercise an actual dictionary lookup, including with changing
            # keys; don't pass merely because a constant result folded away.
            assert any(op.name == 'call_i' and
                       'lookup_function' in op.args[0] for op in loop)
            # Symbol keys need no Ruby hash/eql? callbacks or vrefs.
            assert not [op for op in loop if 'call_may_force' in op.name]
            assert not [op for op in loop if op.name.startswith('new')]
