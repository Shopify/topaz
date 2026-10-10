from .base import BaseJITTest


class TestClosure(BaseJITTest):
    def test_int_closure_cells(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        a = 1
        (1..10_000).each do |i|
          a = i
        end
        """)
        self.assert_matches(self.ruby_loop(traces, "each"), """
        label(p0, p1, p2, p4, p5, p6, p8, p9, i10, p13, i89, p21, p23, p25, p27, p29, p31, p33, p50, i55, p48, p76, p74, p81, descr=TargetToken(140248172659488))
        debug_merge_point(0, 0, 'each at LOAD_DEREF')
        guard_not_invalidated(descr=<Guard0x7f8e128b5830>)
        debug_merge_point(0, 0, 'each at LOAD_SELF')
        debug_merge_point(0, 0, 'each at SEND')
        p92 = force_token()
        debug_merge_point(0, 0, 'each at SEND')
        p93 = force_token()
        setfield_gc(p33, 351, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i95 = int_lt(i89, i55)
        guard_true(i95, descr=<Guard0x7f8e128b5880>)
        debug_merge_point(0, 0, 'each at LOAD_CONST')
        debug_merge_point(0, 0, 'each at SEND')
        p96 = force_token()
        debug_merge_point(0, 0, 'each at JUMP_IF_FALSE')
        debug_merge_point(0, 0, 'each at LOAD_DEREF')
        debug_merge_point(0, 0, 'each at YIELD')
        p97 = force_token()
        enter_portal_frame(31, 6340)
        debug_merge_point(1, 1, 'block in <main> at LOAD_DEREF')
        debug_merge_point(1, 1, 'block in <main> at STORE_DEREF')
        debug_merge_point(1, 1, 'block in <main> at RETURN')
        leave_portal_frame(31)
        debug_merge_point(0, 0, 'each at DISCARD_TOP')
        debug_merge_point(0, 0, 'each at LOAD_DEREF')
        debug_merge_point(0, 0, 'each at SEND')
        p101 = force_token()
        enter_portal_frame(31, 1672)
        debug_merge_point(1, 2, 'succ at LOAD_SELF')
        debug_merge_point(1, 2, 'succ at LOAD_CONST')
        debug_merge_point(1, 2, 'succ at SEND')
        p104 = force_token()
        i106 = int_add(i89, 1)
        debug_merge_point(1, 2, 'succ at RETURN')
        leave_portal_frame(31)
        debug_merge_point(0, 0, 'each at STORE_DEREF')
        debug_merge_point(0, 0, 'each at DISCARD_TOP')
        debug_merge_point(0, 0, 'each at JUMP')
        debug_merge_point(0, 0, 'each at LOAD_DEREF')
        i108 = arraylen_gc(p74, descr=<ArrayP 8>)
        setfield_gc(p81, i89, descr=<FieldS topaz.objects.intobject.W_FixnumObject.inst_intvalue 8 pure>)
        setfield_gc(p33, 9, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        jump(p0, p1, p2, p4, p5, p6, p8, p9, i10, p13, i106, p21, p23, p25, p27, p29, p31, p33, p50, i55, p48, p76, p74, p81, descr=TargetToken(140248172659488))
        """)
