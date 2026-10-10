import pytest

from .base import BaseJITTest


class TestHash(BaseJITTest):
    @pytest.mark.parametrize('key, identity', [
        ('i.to_s', False), ('i.to_s.to_sym', False),
        ('i', False), ('i.to_s', True),
    ])
    def test_flat_map(self, topaz, tmpdir, key, identity):
        traces = self.run(topaz, tmpdir, '''
        def flatten_values(h)
          h.flat_map { |key, value| [value, value + 1] }
        end
        h = {}
        %s
        12.times { |i| h[%s] = i }
        expected = (0...12).to_a.flat_map { |i| [i, i + 1] }
        2000.times do
          raise 'wrong values' unless flatten_values(h) == expected
        end
        keys = h.keys
        h[Object.new]
        h[keys[0]] = 50
        expected[0] = 50
        expected[1] = 51
        2000.times do
          raise 'stale values' unless flatten_values(h) == expected
        end
        ''' % ('h.compare_by_identity' if identity else '', key))
        strategy = ('IdentityDictStrategy' if identity else
                    {'i.to_s': 'StringDictStrategy',
                     'i.to_s.to_sym': 'SymbolDictStrategy',
                     'i': 'ObjectDictStrategy'}[key])
        assert any('Hash#flat_map [%s]' % strategy in trace.trace.comment and
                   'loop with' in trace.trace.comment for trace in traces)
        assert not any('Hash#each ' in trace.trace.comment and
                       'block in collect_concat' in trace.trace.comment
                       for trace in traces)

    def test_flat_map_transition_in_callback(self, topaz, tmpdir):
        self.run(topaz, tmpdir, '''
        3000.times do
          h = {'a' => 1, 'b' => 2, 'c' => 3}
          result = h.flat_map do |key, value|
            if value == 1
              h[Object.new]
              h['b'] = 20
              h.delete('c')
            end
            [value]
          end
          raise 'bad transition' unless result == [1, 20]
        end
        ''')

    def test_flat_map_each_override_after_warmup(self, topaz, tmpdir):
        self.run(topaz, tmpdir, '''
        def flatten(h)
          h.flat_map { |k, v| [v] }
        end
        h = {a: 1, b: 2}
        3000.times { raise 'bad values' unless flatten(h) == [1, 2] }
        def h.each
          yield [:custom, 9]
        end
        3000.times { raise 'ignored override' unless flatten(h) == [9] }
        ''')

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
