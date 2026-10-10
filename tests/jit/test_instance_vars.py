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
        loop = self.ruby_loop(traces)
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
        self.assert_matches(self.ruby_loop(traces), """
        label(p0, p1, p2, p4, p5, p8, p9, i47, p19, p21, p23, p34, descr=TargetToken(132283683470176))
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        guard_not_invalidated(descr=<Guard0x784fb1f27790>)
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p49 = force_token()
        setfield_gc(p23, 31, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i52 = int_lt(i47, 10000)
        guard_true(i52, descr=<Guard0x784fb1f277e0>)
        debug_merge_point(0, 0, '<main> at JUMP_IF_FALSE')
        debug_merge_point(0, 0, '<main> at LOAD_SCOPE')
        debug_merge_point(0, 0, '<main> at LOAD_LOCAL_CONSTANT')
        debug_merge_point(0, 0, '<main> at SEND')
        p54 = force_token()
        p55 = force_token()
        p56 = force_token()
        enter_portal_frame(31, 6340)
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
        leave_portal_frame(31)
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p60 = force_token()
        i62 = int_add(i47, 1)
        debug_merge_point(0, 0, '<main> at STORE_DEREF')
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at JUMP')
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        setfield_gc(p23, 55, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        jump(p0, p1, p2, p4, p5, p8, p9, i62, p19, p21, p23, p34, descr=TargetToken(132283683470176))
        """)

    def test_unboxed_int_storage(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        @i = 0
        while @i < 10000
          @i += 1
        end
        """)
        self.assert_matches(self.ruby_loop(traces), """
        label(p0, p1, p2, p4, p5, p6, p8, p9, p19, p27, f39, p31, descr=TargetToken(140079171533664))
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        guard_not_invalidated(descr=<Guard0x7f66b93f76a0>)
        debug_merge_point(0, 0, '<main> at LOAD_INSTANCE_VAR')
        i42 = convert_float_bytes_to_longlong(f39)
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p43 = force_token()
        setfield_gc(p19, 20, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i46 = int_lt(i42, 10000)
        guard_true(i46, descr=<Guard0x7f66b93f76f0>)
        debug_merge_point(0, 0, '<main> at JUMP_IF_FALSE')
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        debug_merge_point(0, 0, '<main> at DUP_TOP')
        debug_merge_point(0, 0, '<main> at LOAD_INSTANCE_VAR')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p47 = force_token()
        i49 = int_add(i42, 1)
        debug_merge_point(0, 0, '<main> at STORE_INSTANCE_VAR')
        f50 = convert_longlong_bytes_to_float(i49)
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at JUMP')
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        i51 = arraylen_gc(p27, descr=<ArrayF 8>)
        setfield_gc(p19, 36, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        setarrayitem_gc(p27, 0, f50, descr=<ArrayF 8>)
        jump(p0, p1, p2, p4, p5, p6, p8, p9, p19, p27, f50, p31, descr=TargetToken(140079171533664))
        """)

    def test_unboxed_float_storage(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        @data = 0.0
        while @data < 10000.0
          @data += 1.0
        end
        """)
        self.assert_matches(self.ruby_loop(traces), """
        label(p0, p1, p2, p4, p5, p6, p8, p9, p19, p27, f37, p30, descr=TargetToken(123277409680160))
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        guard_not_invalidated(descr=<Guard0x701ec23376a0>)
        debug_merge_point(0, 0, '<main> at LOAD_INSTANCE_VAR')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p40 = force_token()
        setfield_gc(p19, 20, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i43 = float_lt(f37, 10000.000000)
        guard_true(i43, descr=<Guard0x701ec23376f0>)
        debug_merge_point(0, 0, '<main> at JUMP_IF_FALSE')
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        debug_merge_point(0, 0, '<main> at DUP_TOP')
        debug_merge_point(0, 0, '<main> at LOAD_INSTANCE_VAR')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p44 = force_token()
        f46 = float_add(f37, 1.000000)
        debug_merge_point(0, 0, '<main> at STORE_INSTANCE_VAR')
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at JUMP')
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        i47 = arraylen_gc(p27, descr=<ArrayF 8>)
        setfield_gc(p19, 36, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        setarrayitem_gc(p27, 0, f46, descr=<ArrayF 8>)
        jump(p0, p1, p2, p4, p5, p6, p8, p9, p19, p27, f46, p30, descr=TargetToken(123277409680160))
        """)
