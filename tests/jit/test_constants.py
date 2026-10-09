import pytest

from .base import BaseJITTest


class TestConstants(BaseJITTest):
    @pytest.mark.parametrize("owner", ["Holder", "Parent"])
    def test_scoped_constant(self, topaz, tmpdir, owner):
        traces = self.run(topaz, tmpdir, """
        class Parent
        end
        class Holder < Parent
        end
        %s.const_set(:Value, 7)

        def read_constant
          i = 0
          sum = 0
          while i < 10000
            sum += Holder::Value
            i += 1
          end
          sum
        end

        raise 'wrong initial value' unless read_constant == 70000
        # Changing the owner must invalidate the compiled lookup, including
        # when Holder inherits the constant from Parent.
        %s.const_set(:Value, 9)
        raise 'stale compiled constant' unless read_constant == 90000
        """ % (owner, owner))
        loops = [trace.loop for trace in traces
                 if "in read_constant" in trace.trace.comment
                 and "loop with" in trace.trace.comment]
        assert loops
        for loop in loops:
            assert any(op.name == "debug_merge_point" and
                       "LOAD_CONSTANT" in op.args[-1] for op in loop)
            # The constant is folded under invalidation guards, leaving
            # arithmetic rather than a residual superclass-search call.
            assert not [op for op in loop if "call" in op.name]
            assert not [op for op in loop if op.name.startswith("new")]
