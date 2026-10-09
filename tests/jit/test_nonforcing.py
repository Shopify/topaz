import pytest

from .base import BaseJITTest


class TestNonforcingHelpers(BaseJITTest):
    @pytest.mark.parametrize('method', ['tr', 'tr_s'])
    def test_tr(self, topaz, tmpdir, method):
        traces = self.run(topaz, tmpdir, '''
        values = ['hello', 'yellow']
        i = 0
        total = 0
        while i < 20000
          total += values[i & 1].%s('a-z', 'A-Z').length
          i += 1
        end
        raise 'wrong transliteration' unless total == %d
        ''' % (method, 90000 if method == 'tr_s' else 110000))
        self.assert_nonforcing_helper(traces, 'translate_string')

    @pytest.mark.parametrize('method', ['ljust', 'rjust'])
    def test_justify(self, topaz, tmpdir, method):
        traces = self.run(topaz, tmpdir, '''
        i = 0
        total = 0
        while i < 20000
          total += 'abc'.%s(8 + (i & 1), 'xy').length
          i += 1
        end
        raise 'wrong padding' unless total == 170000
        ''' % method)
        self.assert_nonforcing_helper(traces, 'justify_string')

    def test_pow(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, '''
        i = 0
        total = 0
        while i < 20000
          total += 2 ** ((i & 3) + 1)
          i += 1
        end
        raise 'wrong power' unless total == 150000
        ''')
        self.assert_nonforcing_helper(traces, 'pow_positive')

    def test_to_i(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, '''
        values = ['  +123tail', ' -456tail']
        i = 0
        total = 0
        while i < 20000
          total += values[i & 1].to_i
          i += 1
        end
        raise 'wrong integer parsing' unless total == -3330000
        ''')
        self.assert_nonforcing_helper(traces, 'scan_integer_prefix')

    def assert_nonforcing_helper(self, traces, helper):
        calls = [op for trace in traces for op in trace.trace.operations
                 if 'call' in op.name and op.args and helper in op.args[0]]
        assert calls, helper
        assert all('may_force' not in op.name for op in calls), calls

    def test_class_var_base(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, '''
        class Counter
          @@count = 0
          class << self
            def run
              i = 0
              while i < 20000
                @@count += 1
                i += 1
              end
              @@count
            end
          end
        end
        raise 'wrong class variable' unless Counter.run == 20000
        raise 'stale class variable' unless Counter.run == 40000
        ''')
        self.assert_nonforcing_helper(traces, '_class_var_base')

    def test_gcd(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, '''
        i = 1
        total = 0
        while i <= 20000
          total += (i * 6).gcd(18)
          i += 1
        end
        raise 'wrong gcd' unless total == 199992
        ''')
        self.assert_nonforcing_helper(traces, 'gcd_positive')

    def test_rindex(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, '''
        values = ['abcabc', 'xbcxbc']
        i = 0
        total = 0
        while i < 20000
          total += values[i & 1].rindex('bc', 3 + (i & 1))
          i += 1
        end
        raise 'wrong rindex' unless total == 50000
        ''')
        # RPython implements rfind through its shared search helper.
        self.assert_nonforcing_helper(traces, '_search_elidable__str_str')
        assert not any('method_rindex' in op.args[0]
                       for trace in traces for op in trace.trace.operations
                       if 'call' in op.name and op.args)

    @pytest.mark.parametrize('separator,helper', [
        ('', 'split_whitespace'), ("','", 'split_string')])
    def test_split(self, topaz, tmpdir, separator, helper):
        traces = self.run(topaz, tmpdir, """
        values = ['a b,c', 'd e,f']
        i = 0
        total = 0
        while i < 20000
          total += values[i & 1].split(%s).length
          i += 1
        end
        raise 'wrong split' unless total == 40000
        """ % separator)
        self.assert_nonforcing_helper(traces, helper)
        if separator:
            self.assert_nonforcing_helper(traces, 'wrap_split_result')

    def test_gsub_literal(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        values = ['abcabc', 'xbcxbc']
        i = 0
        total = 0
        while i < 20000
          total += values[i & 1].gsub('bc', '!').length
          i += 1
        end
        raise 'wrong gsub' unless total == 80000
        """)
        self.assert_nonforcing_helper(traces, 'replace_string')

    @pytest.mark.parametrize('arguments', ['', "'a-z'"])
    def test_squeeze(self, topaz, tmpdir, arguments):
        traces = self.run(topaz, tmpdir, """
        values = ['aaabbbccc', 'dddeeefff']
        i = 0
        total = 0
        while i < 20000
          total += values[i & 1].squeeze(%s).length
          i += 1
        end
        raise 'wrong squeeze' unless total == 60000
        """ % arguments)
        self.assert_nonforcing_helper(traces, 'squeeze_string')
        if arguments:
            self.assert_nonforcing_helper(traces, 'intersect_squeeze_set')
