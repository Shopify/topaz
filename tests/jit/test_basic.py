from .base import BaseJITTest


class TestBasic(BaseJITTest):
    def test_while_loop(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        i = 0
        while i < 10000
          i += 1
        end
        """)
        self.assert_matches(self.ruby_loop(traces), """
        label(p0, p1, p2, p4, p5, p6, p8, p9, i39, p19, p21, p32, descr=TargetToken(132797350705824))
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        guard_not_invalidated(descr=<Guard0x78c74ae67790>)
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p41 = force_token()
        setfield_gc(p21, 18, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i44 = int_lt(i39, 10000)
        guard_true(i44, descr=<Guard0x78c74ae677e0>)
        debug_merge_point(0, 0, '<main> at JUMP_IF_FALSE')
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p46 = force_token()
        i48 = int_add(i39, 1)
        debug_merge_point(0, 0, '<main> at STORE_DEREF')
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at JUMP')
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        setfield_gc(p21, 32, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        jump(p0, p1, p2, p4, p5, p6, p8, p9, i48, p19, p21, p32, descr=TargetToken(132797350705824))
        """)

    def test_constant_string(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        i = 0
        while i < 10000
          i += "a".length
        end
        """)
        self.assert_matches(self.ruby_loop(traces), """
        label(p0, p1, p2, p4, p5, p6, p8, p9, i40, p19, p21, p32, descr=TargetToken(130685221100192))
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        guard_not_invalidated(descr=<Guard0x76db862a5740>)
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p42 = force_token()
        setfield_gc(p21, 18, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i45 = int_lt(i40, 10000)
        guard_true(i45, descr=<Guard0x76db862a5790>)
        debug_merge_point(0, 0, '<main> at JUMP_IF_FALSE')
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at COERCE_STRING')
        debug_merge_point(0, 0, '<main> at SEND')
        p47 = force_token()
        debug_merge_point(0, 0, '<main> at SEND')
        p48 = force_token()
        i50 = int_add(i40, 1)
        debug_merge_point(0, 0, '<main> at STORE_DEREF')
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at JUMP')
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        setfield_gc(p21, 38, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        jump(p0, p1, p2, p4, p5, p6, p8, p9, i50, p19, p21, p32, descr=TargetToken(130685221100192))
        """)

    def test_method_missing(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        i = 0
        while i < 10000
          Array.try_convert(1)
          i += 1
        end
        """)
        self.assert_matches(self.ruby_loop(traces), """
        label(p0, p1, p2, p4, p5, p8, p9, i49, p19, p21, p32, descr=TargetToken(126646298508128))
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        guard_not_invalidated(descr=<Guard0x732f239e7790>)
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p51 = force_token()
        setfield_gc(p21, 18, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i54 = int_lt(i49, 10000)
        guard_true(i54, descr=<Guard0x732f239e77e0>)
        debug_merge_point(0, 0, '<main> at JUMP_IF_FALSE')
        debug_merge_point(0, 0, '<main> at LOAD_SCOPE')
        debug_merge_point(0, 0, '<main> at LOAD_LOCAL_CONSTANT')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p55 = force_token()
        enter_portal_frame(31, 340)
        debug_merge_point(1, 1, 'try_convert at LOAD_SCOPE')
        debug_merge_point(1, 1, 'try_convert at LOAD_LOCAL_CONSTANT')
        debug_merge_point(1, 1, 'try_convert at LOAD_DEREF')
        debug_merge_point(1, 1, 'try_convert at LOAD_SCOPE')
        debug_merge_point(1, 1, 'try_convert at LOAD_LOCAL_CONSTANT')
        debug_merge_point(1, 1, 'try_convert at LOAD_CONST')
        debug_merge_point(1, 1, 'try_convert at SEND')
        p58 = force_token()
        debug_merge_point(1, 1, 'try_convert at RETURN')
        leave_portal_frame(31)
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p60 = force_token()
        i62 = int_add(i49, 1)
        debug_merge_point(0, 0, '<main> at STORE_DEREF')
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at JUMP')
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        setfield_gc(p21, 45, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        jump(p0, p1, p2, p4, p5, p8, p9, i62, p19, p21, p32, descr=TargetToken(126646298508128))
        """)
