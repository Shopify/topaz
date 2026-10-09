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

    def test_append_indexed_character(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, '''
        def append_characters(table)
          out = ''
          i = 0
          while i < 20000
            out << table[i & 3]
            i += 1
          end
          out
        end
        raise 'wrong output' unless append_characters('abcd') == 'abcd' * 5000
        ''')
        self.assert_no_temporary_character_strings(traces, 'in append_characters')

    @pytest.mark.parametrize('mutable', [False, True])
    def test_base64_native(self, topaz, tmpdir, mutable):
        traces = self.run(topaz, tmpdir, '''
        def encode_loop(source, expected)
          i = 0
          while i < 10000
            raise 'wrong base64' unless [source].pack('m0') == expected
            i += 1
          end
        end
        source = 'foobar' * 32
        %s
        encode_loop(source, 'Zm9vYmFy' * 32)
        source.setbyte(0, 103)
        encode_loop(source, 'Z29vYmFy' + 'Zm9vYmFy' * 31)
        raise 'wrong padding' unless ['f'].pack('m0') == 'Zg=='
        raise 'wrong padding' unless ['fo'].pack('m0') == 'Zm8='
        ''' % ("source << ''" if mutable else ''))
        assert any('call' in op.name and 'base64_encode__' in op.args[0]
                   for trace in traces for op in trace.trace.operations)
        # There must be no traced Ruby byte loop in the Base64 wrapper.
        assert not [trace for trace in traces
                    if 'in base64_encode' in trace.trace.comment
                    and 'loop with' in trace.trace.comment]

    def test_base64_in_place_mutation(self, topaz, tmpdir):
        self.run(topaz, tmpdir, '''
        s = "\\x00\\x00\\x00"
        s << ''
        i = 0
        while i < 10000
          s.setbyte(0, i & 1)
          expected = (i & 1) == 0 ? 'AAAA' : 'AQAA'
          raise 'cached base64 result' unless [s].pack('m0') == expected
          i += 1
        end
        ''')

    def assert_no_temporary_character_strings(self, traces, location):
        loops = [trace.loop for trace in traces
                 if location in trace.trace.comment
                 and 'loop with' in trace.trace.comment]
        assert loops
        for loop in loops:
            assert any(op.name == 'strgetitem' for op in loop)
            assert not [op for op in loop if op.name == 'newstr']
            assert not [op for op in loop if 'call' in op.name and
                        any('ll_extend_with_str' in arg for arg in op.args)]

    @pytest.mark.parametrize('mutable', [False, True])
    @pytest.mark.parametrize('length', [1, 128])
    def test_ascii_only(self, topaz, tmpdir, mutable, length):
        traces = self.run(topaz, tmpdir, '''
        def check_ascii(s)
          i = 0
          count = 0
          while i < 10000
            count += 1 if s.ascii_only?
            i += 1
          end
          count
        end
        s = 'a' * %d
        %s
        raise 'wrong ASCII result' unless check_ascii(s) == 10000
        s.setbyte(0, 128)
        raise 'stale ASCII result' unless check_ascii(s) == 0
        s.setbyte(0, 97)
        raise 'stale non-ASCII result' unless check_ascii(s) == 10000
        ''' % (length, "s << ''" if mutable else ''))
        matches = [trace for trace in traces
                   if 'in check_ascii' in trace.trace.comment
                   and 'loop with' in trace.trace.comment]
        assert matches
        for trace in matches:
            assert any('call' in op.name and 'ascii_only_' in op.args[0]
                       for op in trace.trace.operations)
            loop = trace.loop
            calls = [op for op in loop if 'call' in op.name]
            assert all(op.name in ('call_i', 'call_pure_i') and
                       'ascii_only_' in op.args[0] for op in calls)
            assert not [op for op in loop if op.name.startswith('new')]
            assert not [op for op in loop if op.name in
                        ('strgetitem', 'getarrayitem_gc_i', 'enter_portal_frame')]

    def test_ascii_only_in_place_mutation(self, topaz, tmpdir):
        self.run(topaz, tmpdir, '''
        s = 'aaaa'
        s << ''
        i = 0
        count = 0
        while i < 20000
          s.setbyte(3, 127 + (i & 1))
          count += 1 if s.ascii_only?
          i += 1
        end
        raise 'cached mutable scan' unless count == 10000
        ''')

    @pytest.mark.parametrize('mutable', [False, True])
    def test_unpack_hex(self, topaz, tmpdir, mutable):
        traces = self.run(topaz, tmpdir, '''
        def hex_loop(s, expected)
          i = 0
          while i < 10000
            result = s.__topaz_unpack_hex(0, 128, true)
            raise 'wrong hex' unless result == expected
            i += 1
          end
        end
        s = "\\x12\\xab" * 32
        %s
        hex_loop(s, '12ab' * 32)
        s.setbyte(0, 255)
        hex_loop(s, 'ffab' + '12ab' * 31)
        ''' % ("s << ''" if mutable else ''))
        matches = [trace for trace in traces
                   if 'in hex_loop' in trace.trace.comment
                   and 'loop with' in trace.trace.comment]
        assert matches
        for trace in matches:
            loop = trace.loop
            assert any('call' in op.name and 'unpack_hex' in op.args[0]
                       for op in loop)
            # Hex digit selection and input scanning belong inside the helper.
            assert not [op for op in loop if op.name in
                        ('strgetitem', 'getarrayitem_gc_i', 'int_rshift', 'int_and')]
            assert not [op for op in loop if op.name == 'newstr']

    @pytest.mark.parametrize('mutable', [False, True])
    def test_unpack_integer(self, topaz, tmpdir, mutable):
        traces = self.run(topaz, tmpdir, '''
        def integer_loop(values)
          i = 0
          sum = 0
          while i < 10000
            sum += values[i & 1].__topaz_unpack_integer(0, 4, true, false)
            i += 1
          end
          sum
        end
        values = ["\\x01\\x02\\x03\\x04", "\\x05\\x06\\x07\\x08"]
        %s
        raise 'wrong integers' unless integer_loop(values) == (16909060 + 84281096) * 5000
        values[0].setbyte(3, 5)
        raise 'stale integer' unless integer_loop(values) == (16909061 + 84281096) * 5000
        ''' % ("values.each { |s| s << '' }" if mutable else ''))
        matches = [trace for trace in traces
                   if 'in integer_loop' in trace.trace.comment
                   and 'loop with' in trace.trace.comment]
        assert matches
        for trace in matches:
            loop = trace.loop
            # A known-width read is straight-line byte loads/arithmetic, with
            # no decoder call and no intermediate boxed shift/or results.
            assert any(op.name in ('strgetitem', 'getarrayitem_gc_i') for op in loop)
            assert not [op for op in loop if 'call' in op.name]
            assert not [op for op in loop if op.name.startswith('new')]

    def test_unpack_integer_in_place_mutation(self, topaz, tmpdir):
        self.run(topaz, tmpdir, '''
        s = "\\x01\\x02"
        s << ''
        i = 0
        sum = 0
        while i < 10000
          s.setbyte(1, i & 1)
          sum += s.__topaz_unpack_integer(0, 2, true, false)
          i += 1
        end
        raise 'cached integer' unless sum == (256 + 257) * 5000
        ''')
