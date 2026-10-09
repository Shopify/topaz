from .base import BaseJITTest


class TestNonforcingHelpers(BaseJITTest):
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
