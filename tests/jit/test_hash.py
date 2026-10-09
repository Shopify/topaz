import pytest

from .base import BaseJITTest


class TestHash(BaseJITTest):
    @pytest.mark.parametrize('stored_mutable', [False, True])
    @pytest.mark.parametrize('lookup_mutable', [False, True])
    def test_string_lookup(self, topaz, tmpdir, stored_mutable, lookup_mutable):
        traces = self.run(topaz, tmpdir, '''
        def lookup(h, keys)
          i = 0
          total = 0
          while i < 10000
            total += h[keys[i & 1]]
            i += 1
          end
          total
        end
        a, b = 'a', 'b'
        %s
        h = {a => 1, b => 2}
        keys = ['a', 'b']
        %s
        raise 'wrong value' unless lookup(h, keys) == 15000
        h['b'] = 3
        raise 'stale value' unless lookup(h, keys) == 20000
        keys[1][0] = 'a'
        raise 'stale key contents' unless lookup(h, keys) == 10000
        ''' % ('a << ""; b << ""' if stored_mutable else '',
               'keys.each { |key| key << "" }' if lookup_mutable else ''))
        loops = [trace.loop for trace in traces
                 if 'in lookup' in trace.trace.comment
                 and 'loop with' in trace.trace.comment]
        assert loops
        for loop in loops:
            assert any(op.name == 'call_i' and
                       'lookup_function' in op.args[0] for op in loop)
            assert not [op for op in loop if 'call_may_force' in op.name]
            assert not [op for op in loop if op.name.startswith('new')]

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
