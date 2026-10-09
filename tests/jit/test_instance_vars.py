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
        label(p0, p1, p2, p4, p5, p6, p9, p10, i11, i48, p20, p22, p24, p35, descr=TargetToken(132283683470176))
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        guard_not_invalidated(descr=<Guard0x784fb1f27790>)
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p50 = force_token()
        setfield_gc(p24, 34, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i53 = int_lt(i48, 10000)
        guard_true(i53, descr=<Guard0x784fb1f277e0>)
        debug_merge_point(0, 0, '<main> at JUMP_IF_FALSE')
        debug_merge_point(0, 0, '<main> at LOAD_SCOPE')
        debug_merge_point(0, 0, '<main> at LOAD_LOCAL_CONSTANT')
        debug_merge_point(0, 0, '<main> at SEND')
        p55 = force_token()
        p56 = force_token()
        p57 = force_token()
        enter_portal_frame(30, 6444)
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
        leave_portal_frame(30)
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p61 = force_token()
        i63 = int_add(i48, 1)
        debug_merge_point(0, 0, '<main> at STORE_DEREF')
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at JUMP')
        debug_merge_point(0, 0, '<main> at LOAD_DEREF')
        setfield_gc(p24, 58, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        jump(p0, p1, p2, p4, p5, p6, p9, p10, i11, i63, p20, p22, p24, p35, descr=TargetToken(132283683470176))
        """)

    def test_unboxed_int_storage(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        @i = 0
        while @i < 10000
          @i += 1
        end
        """)
        self.assert_matches(self.ruby_loop(traces), """
        label(p0, p1, p2, p4, p5, p6, p7, p9, p10, i11, p20, p28, f40, p32, descr=TargetToken(140079171533664))
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        guard_not_invalidated(descr=<Guard0x7f66b93f76a0>)
        debug_merge_point(0, 0, '<main> at LOAD_INSTANCE_VAR')
        i43 = convert_float_bytes_to_longlong(f40)
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p44 = force_token()
        setfield_gc(p20, 23, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i47 = int_lt(i43, 10000)
        guard_true(i47, descr=<Guard0x7f66b93f76f0>)
        debug_merge_point(0, 0, '<main> at JUMP_IF_FALSE')
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        debug_merge_point(0, 0, '<main> at DUP_TOP')
        debug_merge_point(0, 0, '<main> at LOAD_INSTANCE_VAR')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p48 = force_token()
        i50 = int_add(i43, 1)
        debug_merge_point(0, 0, '<main> at STORE_INSTANCE_VAR')
        f51 = convert_longlong_bytes_to_float(i50)
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at JUMP')
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        i52 = arraylen_gc(p28, descr=<ArrayF 8>)
        setfield_gc(p20, 39, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        setarrayitem_gc(p28, 0, f51, descr=<ArrayF 8>)
        jump(p0, p1, p2, p4, p5, p6, p7, p9, p10, i11, p20, p28, f51, p32, descr=TargetToken(140079171533664))
        """)

    def test_unboxed_float_storage(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, """
        @data = 0.0
        while @data < 10000.0
          @data += 1.0
        end
        """)
        self.assert_matches(self.ruby_loop(traces), """
        label(p0, p1, p2, p4, p5, p6, p7, p9, p10, i11, p20, p28, f38, p31, descr=TargetToken(123277409680160))
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        guard_not_invalidated(descr=<Guard0x701ec23376a0>)
        debug_merge_point(0, 0, '<main> at LOAD_INSTANCE_VAR')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p41 = force_token()
        setfield_gc(p20, 23, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        i44 = float_lt(f38, 10000.000000)
        guard_true(i44, descr=<Guard0x701ec23376f0>)
        debug_merge_point(0, 0, '<main> at JUMP_IF_FALSE')
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        debug_merge_point(0, 0, '<main> at DUP_TOP')
        debug_merge_point(0, 0, '<main> at LOAD_INSTANCE_VAR')
        debug_merge_point(0, 0, '<main> at LOAD_CONST')
        debug_merge_point(0, 0, '<main> at SEND')
        p45 = force_token()
        f47 = float_add(f38, 1.000000)
        debug_merge_point(0, 0, '<main> at STORE_INSTANCE_VAR')
        debug_merge_point(0, 0, '<main> at DISCARD_TOP')
        debug_merge_point(0, 0, '<main> at JUMP')
        debug_merge_point(0, 0, '<main> at LOAD_SELF')
        i48 = arraylen_gc(p28, descr=<ArrayF 8>)
        setfield_gc(p20, 39, descr=<FieldS topaz.executioncontext.ExecutionContext.inst_last_instr 24>)
        setarrayitem_gc(p28, 0, f47, descr=<ArrayF 8>)
        jump(p0, p1, p2, p4, p5, p6, p7, p9, p10, i11, p20, p28, f47, p31, descr=TargetToken(123277409680160))
        """)
