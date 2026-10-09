from .base import BaseJITTest


class TestArray(BaseJITTest):
    def test_subscript_assign_simple(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        arr = [false]
        10000.times { arr[0] = true }
        """)
        self.assert_matches(self.ruby_loop(traces, "times"), """
        label(p0, p1, p2, p4, p5, p6, p7, p9, p10, i11, p14, i84, p22, p24, p26, p28, i45, p42, p63, p68, p76, p61, p80, descr=TargetToken(136973925417888))
        debug_merge_point(0, 0, 'times at LOAD_DEREF')
        guard_not_invalidated(descr=<Guard0x7c93ba3377e0>)
        debug_merge_point(0, 0, 'times at LOAD_SELF')
        debug_merge_point(0, 0, 'times at SEND')
        p88 = force_token()
        setfield_gc(p28, 42, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i90 = int_lt(i84, i45)
        guard_true(i90, descr=<Guard0x7c93ba337830>)
        debug_merge_point(0, 0, 'times at JUMP_IF_FALSE')
        debug_merge_point(0, 0, 'times at LOAD_DEREF')
        debug_merge_point(0, 0, 'times at YIELD')
        p91 = force_token()
        enter_portal_frame(30, 6444)
        debug_merge_point(1, 1, 'block in <main> at LOAD_DEREF')
        debug_merge_point(1, 1, 'block in <main> at LOAD_CONST')
        debug_merge_point(1, 1, 'block in <main> at BUILD_ARRAY')
        debug_merge_point(1, 1, 'block in <main> at LOAD_CONST')
        debug_merge_point(1, 1, 'block in <main> at BUILD_ARRAY')
        debug_merge_point(1, 1, 'block in <main> at SEND_SPLAT')
        p94 = force_token()
        debug_merge_point(1, 1, 'block in <main> at RETURN')
        leave_portal_frame(30)
        debug_merge_point(0, 0, 'times at DISCARD_TOP')
        debug_merge_point(0, 0, 'times at LOAD_DEREF')
        debug_merge_point(0, 0, 'times at LOAD_CONST')
        debug_merge_point(0, 0, 'times at SEND')
        p96 = force_token()
        i98 = int_add(i84, 1)
        debug_merge_point(0, 0, 'times at STORE_DEREF')
        debug_merge_point(0, 0, 'times at DISCARD_TOP')
        debug_merge_point(0, 0, 'times at JUMP')
        debug_merge_point(0, 0, 'times at LOAD_DEREF')
        i99 = arraylen_gc(p61, descr=<ArrayP 8>)
        i100 = arraylen_gc(p80, descr=<ArrayP 8>)
        setfield_gc(p28, 63, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        jump(p0, p1, p2, p4, p5, p6, p7, p9, p10, i11, p14, i98, p22, p24, p26, p28, i45, p42, p63, p68, p76, p61, p80, descr=TargetToken(136973925417888))
        """)
