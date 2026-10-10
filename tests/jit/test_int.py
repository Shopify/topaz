import pytest

from .base import BaseJITTest


class TestInteger(BaseJITTest):
    def test_equality_does_not_order_operands(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        values = [1, 7, 3, 7]
        i = 0
        matches = 0
        while i < 20000
          matches += 1 if values[i & 3] == 3
          i += 1
        end
        raise 'wrong equality' unless matches == 5000
        """)
        loop = self.ruby_loop(traces)
        # The loop bound may use int_lt; comparing an element with 3 must
        # use equality directly, without comparator's less/greater branches.
        assert any(op.name in ('int_eq', 'int_ne') and '3' in op.args
                   for op in loop)
        assert not any(op.name in ('int_lt', 'int_le', 'int_gt', 'int_ge')
                       and '3' in op.args for op in loop)

    @pytest.mark.parametrize("start, limit, step", [
        (1, 20000, 2),
        (19999, 0, -2),
    ])
    def test_step(self, topaz, tmpdir, start, limit, step):
        traces = self.run(topaz, tmpdir, """
        sum = 0
        count = 0
        result = %d.step(%d, %d) do |i|
          sum += i
          count += 1
        end
        raise 'wrong sum' unless sum == 100000000
        raise 'wrong count' unless count == 10000
        raise 'wrong return value' unless result == %d
        """ % (start, limit, step, start))
        step_loops = [trace for trace in traces
                      if "Integer#step" in trace.trace.comment
                      and "t.rb:" in trace.trace.comment
                      and "loop with" in trace.trace.comment]
        assert len(step_loops) == 1
        loop = step_loops[0].loop
        # The block is inlined into the builtin's loop: sum, count and the
        # induction variable use checked integer adds, without calls or boxes.
        self.assert_matches(loop, """
        label(i0, i1, i51, p3, p24, p22, p20, p18, p5, p12, p14, p10, p8, p6, p7, p25, p35, i40, p43, p16, descr=TargetToken(135997521828320))
        debug_merge_point(0, 0, 'block in <main>')
        p55 = force_token()
        guard_not_invalidated(descr=<Guard0x7bb063fa7b50>)
        enter_portal_frame(30, 6444)
        debug_merge_point(1, 1, 'block in <main> at LOAD_DEREF')
        debug_merge_point(1, 1, 'block in <main> at LOAD_DEREF')
        debug_merge_point(1, 1, 'block in <main> at SEND')
        p58 = force_token()
        setfield_gc(p24, 11, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i60 = int_add_ovf(i40, i51)
        guard_no_overflow(descr=<Guard0x7bb063fa7ba0>)
        debug_merge_point(1, 1, 'block in <main> at STORE_DEREF')
        debug_merge_point(1, 1, 'block in <main> at DISCARD_TOP')
        debug_merge_point(1, 1, 'block in <main> at LOAD_DEREF')
        setfield_gc(p35, i60, descr=<FieldS topaz.objects.intobject.W_FixnumObject.inst_intvalue 8 pure>)
        i61 = getfield_gc_i(p43, descr=<FieldS topaz.objects.intobject.W_FixnumObject.inst_intvalue 8 pure>)
        debug_merge_point(1, 1, 'block in <main> at LOAD_CONST')
        debug_merge_point(1, 1, 'block in <main> at SEND')
        p62 = force_token()
        setfield_gc(p24, 26, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i65 = int_add_ovf(i61, 1)
        guard_no_overflow(descr=<Guard0x7bb063fa7bf0>)
        debug_merge_point(1, 1, 'block in <main> at STORE_DEREF')
        debug_merge_point(1, 1, 'block in <main> at RETURN')
        leave_portal_frame(30)
        setfield_gc(p43, i65, descr=<FieldS topaz.objects.intobject.W_FixnumObject.inst_intvalue 8 pure>)
        i67 = int_add_ovf(i51, i1)
        guard_no_overflow(descr=<Guard0x7bb063fa7c40>)
        i68 = %s(i67, i0)
        guard_true(i68, descr=<Guard0x7bb063f344b8>)
        debug_merge_point(0, 0, 'block in <main>')
        i69 = arraylen_gc(p16, descr=<ArrayP 8>)
        jump(i0, i1, i67, p3, p24, p22, p20, p18, p5, p12, p14, p10, p8, p6, p7, p25, p35, i60, p43, p16, descr=TargetToken(135997521828320))
        """ % ("int_le" if step > 0 else "int_ge"))
