from .base import BaseJITTest


class TestInstanceVars(BaseJITTest):
    def test_two_inline_boxed_fields(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        class Pair
          attr_accessor :left, :right
        end
        a = Pair.new
        b = Pair.new
        a.left = b
        a.right = a
        b.left = a
        b.right = b
        node = a
        i = 0
        while i < 10_000
          following = node.left
          node.left = node.right
          node.right = following
          node = following
          i += 1
        end
        raise 'lost a link' if a.left.equal?(a.right)
        raise 'lost a link' if b.left.equal?(b.right)
        """)
        # Bootstrapping also produces regexp traces before our Ruby loop.
        ruby_loops = [trace for trace in traces
                      if "t.rb:" in trace.trace.comment
                      and ":in <main>" in trace.trace.comment
                      and "loop with" in trace.trace.comment]
        assert len(ruby_loops) == 1
        loop = ruby_loops[0].loop
        # Both boxed slots should be accessed directly on the object, with
        # no backing-array accesses or allocations in the steady-state loop.
        storage_ops = []
        for op in loop:
            for field in ("inst_object_storage", "inst_unboxed_storage"):
                if field in str(op.descr):
                    storage_ops.append((op.name, field))
        assert sorted(storage_ops) == sorted([
            ("getfield_gc_r", "inst_object_storage"),
            ("getfield_gc_r", "inst_unboxed_storage"),
            ("setfield_gc", "inst_object_storage"),
            ("setfield_gc", "inst_unboxed_storage"),
        ])
        assert not any(op.name.startswith(("getarrayitem", "setarrayitem", "new"))
                       for op in loop)

    def test_initialize(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        class A
          def initialize
            @a = 1
            @b = 2
            @c = 3
          end
        end
        i = 0
        while i < 10000
          A.new
          i += 1
        end
        """)
        self.assert_matches(traces[0].loop, """
        label(p0, p1, p2, p4, p6, p9, p10, i43, p19, p22, p24, descr=TargetToken(140691297408272))
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        setfield_gc(p24, 34, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        guard_not_invalidated(descr=<Guard0x7ff53edb8f90>)
        p46 = force_token()
        i48 = int_lt(i43, 10000)
        guard_true(i48, descr=<Guard0x7ff53ecf9658>)
        debug_merge_point(0, 0, '<main> at JUMP_IF_FALSE')
        debug_merge_point(0, 0, '<main> at LOAD_SCOPE')
        debug_merge_point(0, 0, '<main> at LOAD_LOCAL_CONSTANT')
        debug_merge_point(0, 0, '<main> at SEND')
        p49 = force_token()
        p50 = force_token()
        p51 = force_token()
        enter_portal_frame(0, 0)
        debug_merge_point(1, 1, 'initialize at LOAD_SELF')
        debug_merge_point(1, 1, 'initialize at LOAD_CONST')
        debug_merge_point(1, 1, 'initialize at STORE_INSTANCE_VAR')
        debug_merge_point(1, 1, 'initialize at DISCARD_TOP')
        debug_merge_point(1, 1, 'initialize at LOAD_SELF')
        debug_merge_point(1, 1, 'initialize at LOAD_CONST')
        debug_merge_point(1, 1, 'initialize at STORE_INSTANCE_VAR')
        debug_merge_point(1, 1, 'initialize at DISCARD_TOP')
        debug_merge_point(1, 1, 'initialize at LOAD_SELF')
        debug_merge_point(1, 1, 'initialize at LOAD_CONST')
        debug_merge_point(1, 1, 'initialize at STORE_INSTANCE_VAR')
        debug_merge_point(1, 1, 'initialize at RETURN')
        leave_portal_frame(0)
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p55 = force_token()
        i57 = int_add(i43, 1)
        debug_merge_point(0, 0, '<main> at STORE_DEREF')
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at JUMP')
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        setfield_gc(p24, 58, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        jump(p0, p1, p2, p4, p6, p9, p10, i57, p19, p22, p24, descr=TargetToken(140691297408272))
        """)

    def test_unboxed_int_storage(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        @i = 0
        while @i < 10000
          @i += 1
        end
        """)
        self.assert_matches(traces[0].loop, """
        label(p0, p1, p2, p4, p6, p7, p9, p10, p20, p26, f38, descr=TargetToken(140220342079424))
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        debug_merge_point(0, 0, '<main> at LOAD_INSTANCE_VAR')
        i41 = convert_float_bytes_to_longlong(f38)
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        setfield_gc(p20, 23, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        guard_not_invalidated(descr=<Guard0x7f8797bb8df0>)
        p43 = force_token()
        i45 = int_lt(i41, 10000)
        guard_true(i45, descr=<Guard0x7f8797af8ba8>)
        debug_merge_point(0, 0, '<main> at JUMP_IF_FALSE')
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        debug_merge_point(0, 0, '<main> at DUP_TOP')
        debug_merge_point(0, 0, '<main> at LOAD_INSTANCE_VAR')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p46 = force_token()
        i48 = int_add(i41, 1)
        debug_merge_point(0, 0, '<main> at STORE_INSTANCE_VAR')
        f49 = convert_longlong_bytes_to_float(i48)
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at JUMP')
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        i50 = arraylen_gc(p26, descr=<ArrayF 8>)
        setfield_gc(p20, 39, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        setarrayitem_gc(p26, 0, f49, descr=<ArrayF 8>)
        jump(p0, p1, p2, p4, p6, p7, p9, p10, p20, p26, f49, descr=TargetToken(140220342079424))
        """)

    def test_unboxed_float_storage(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        @data = 0.0
        while @data < 10000.0
          @data += 1.0
        end
        """)
        self.assert_matches(traces[0].loop, """
        label(p0, p1, p2, p4, p6, p7, p9, p10, p20, p26, f36, descr=TargetToken(139792504197136))
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        debug_merge_point(0, 0, '<main> at LOAD_INSTANCE_VAR')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        setfield_gc(p20, 23, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        guard_not_invalidated(descr=<Guard0x7f23fa9b8df0>)
        p40 = force_token()
        i42 = float_lt(f36, 10000.000000)
        guard_true(i42, descr=<Guard0x7f23fa8f8ba8>)
        debug_merge_point(0, 0, '<main> at JUMP_IF_FALSE')
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        debug_merge_point(0, 0, '<main> at DUP_TOP')
        debug_merge_point(0, 0, '<main> at LOAD_INSTANCE_VAR')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p43 = force_token()
        f45 = float_add(f36, 1.000000)
        debug_merge_point(0, 0, '<main> at STORE_INSTANCE_VAR')
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at JUMP')
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        i46 = arraylen_gc(p26, descr=<ArrayF 8>)
        setfield_gc(p20, 39, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        setarrayitem_gc(p26, 0, f45, descr=<ArrayF 8>)
        jump(p0, p1, p2, p4, p6, p7, p9, p10, p20, p26, f45, descr=TargetToken(139792504197136))
        """)
