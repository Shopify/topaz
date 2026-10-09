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
        label(p0, p1, p2, p4, p5, p6, p7, p9, p10, i11, p14, i100, p22, p24, p26, p28, p30, p32, p34, p36, p38, p40, p42, p44, p61, i66, p59, p87, p85, p92, descr=TargetToken(140248172659488))
        debug_merge_point(0, 0, 'each at LOAD_DEREF')
        guard_not_invalidated(descr=<Guard0x7f8e128b5830>)
        debug_merge_point(0, 0, 'each at LOAD_SELF')
        debug_merge_point(0, 0, 'each at SEND')
        p103 = force_token()
        debug_merge_point(0, 0, 'each at SEND')
        p104 = force_token()
        setfield_gc(p44, 362, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i106 = int_lt(i100, i66)
        guard_true(i106, descr=<Guard0x7f8e128b5880>)
        debug_merge_point(0, 0, 'each at LOAD_CONST')
        debug_merge_point(0, 0, 'each at SEND')
        p107 = force_token()
        debug_merge_point(0, 0, 'each at JUMP_IF_FALSE')
        debug_merge_point(0, 0, 'each at LOAD_DEREF')
        debug_merge_point(0, 0, 'each at YIELD')
        p108 = force_token()
        enter_portal_frame(30, 6444)
        debug_merge_point(1, 1, 'block in <main> at LOAD_DEREF')
        debug_merge_point(1, 1, 'block in <main> at STORE_DEREF')
        debug_merge_point(1, 1, 'block in <main> at RETURN')
        leave_portal_frame(30)
        debug_merge_point(0, 0, 'each at DISCARD_TOP')
        debug_merge_point(0, 0, 'each at LOAD_DEREF')
        debug_merge_point(0, 0, 'each at SEND')
        p112 = force_token()
        enter_portal_frame(30, 1696)
        debug_merge_point(1, 2, 'succ at LOAD_SELF')
        debug_merge_point(1, 2, 'succ at LOAD_CONST')
        debug_merge_point(1, 2, 'succ at SEND')
        p115 = force_token()
        i117 = int_add(i100, 1)
        debug_merge_point(1, 2, 'succ at RETURN')
        leave_portal_frame(30)
        debug_merge_point(0, 0, 'each at STORE_DEREF')
        debug_merge_point(0, 0, 'each at DISCARD_TOP')
        debug_merge_point(0, 0, 'each at JUMP')
        debug_merge_point(0, 0, 'each at LOAD_DEREF')
        i119 = arraylen_gc(p85, descr=<ArrayP 8>)
        setfield_gc(p92, i100, descr=<FieldS topaz.objects.intobject.W_FixnumObject.inst_intvalue 8 pure>)
        setfield_gc(p44, 9, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        jump(p0, p1, p2, p4, p5, p6, p7, p9, p10, i11, p14, i117, p22, p24, p26, p28, p30, p32, p34, p36, p38, p40, p42, p44, p61, i66, p59, p87, p85, p92, descr=TargetToken(140248172659488))
        """)
