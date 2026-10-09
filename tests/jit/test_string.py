import pytest

from .base import BaseJITTest


class TestString(BaseJITTest):
    @pytest.mark.parametrize('method, arguments', [
        ('start_with?', 'affix'),
        ('end_with?', 'affix'),
        ('start_with?', '"xx", affix'),
        ('end_with?', '"xx", affix'),
    ])
    @pytest.mark.parametrize('mutable', [False, True])
    @pytest.mark.parametrize('mutable_affix', [False, True])
    def test_affix(self, topaz, tmpdir, method, arguments, mutable, mutable_affix):
        traces = self.run(topaz, tmpdir, '''
        def check_affix(s, affix)
          i = 0
          count = 0
          while i < 10000
            count += 1 if s.%s(%s)
            i += 1
          end
          count
        end
        s = 'abxyz'
        affix = '%s'
        %s
        %s
        raise 'wrong match' unless check_affix(s, affix) == 10000
        s.replace('other')
        raise 'stale match' unless check_affix(s, affix) == 0
        ''' % (method, arguments, 'ab' if method == 'start_with?' else 'yz',
               "s << ''" if mutable else '',
               "affix << ''" if mutable_affix else ''))
        matches = [trace for trace in traces
                   if 'in check_affix' in trace.trace.comment
                   and 'loop with' in trace.trace.comment]
        assert matches
        for trace in matches:
            # An elidable immutable comparison may be hoisted to the preamble.
            assert any('call' in op.name and
                       ('compare_affix' in op.args[0] or 'startswith' in op.args[0])
                       for op in trace.trace.operations)
            loop = trace.loop
            calls = [op for op in loop if 'call' in op.name]
            assert all(op.name in ('call_i', 'call_pure_i') and
                       ('compare_affix' in op.args[0] or 'startswith' in op.args[0])
                       for op in calls)
            # Character comparisons belong in the helper, not in the trace.
            assert not [op for op in loop if op.name == 'strgetitem']
            assert not [op for op in loop if op.name.startswith('new')]

    @pytest.mark.parametrize('method, index', [('start_with?', 0), ('end_with?', 3)])
    @pytest.mark.parametrize('mutate_affix', [False, True])
    def test_affix_in_place_mutation(self, topaz, tmpdir, method, index, mutate_affix):
        self.run(topaz, tmpdir, '''
        def changing_affix(s, affix)
          i = 0
          count = 0
          while i < 20000
            %s.setbyte(%d, 97 + (i & 1))
            count += 1 if s.%s(affix)
            i += 1
          end
          count
        end
        s = 'aaaa'
        affix = 'aa'
        s << ''
        affix << ''
        raise 'cached mutable comparison' unless changing_affix(s, affix) == 10000
        ''' % ('affix' if mutate_affix else 's',
               (index // 2) if mutate_affix else index, method))
