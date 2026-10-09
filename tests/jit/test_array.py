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

    def test_bsearch_index(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, '''
        class Transition
          attr_reader :timestamp_value
          def initialize(value); @timestamp_value = value; end
        end
        def search(transitions)
          i = 0
          sum = 0
          expected = 0
          while i < 20000
            target = (i * 37) % 513
            timestamp = target * 86400 - 1
            index = transitions.bsearch_index do |transition|
              transition.timestamp_value >= timestamp
            end
            sum += index || 512
            expected += target
            i += 1
          end
          raise 'wrong search result' unless sum == expected
        end
        search(Array.new(512) { |i| Transition.new(i * 86400) })
        ''')
        searches = [trace for trace in traces
                    if 'Array#bsearch_index' in trace.trace.comment
                    and 'loop with' in trace.trace.comment]
        assert searches
        continuing_bridges = []
        for trace in searches:
            loop = trace.loop
            ops = [op for op in loop if op.name not in
                   ('debug_merge_point', 'enter_portal_frame', 'leave_portal_frame')]
            # One search step with an inlined callback, not an unrolled search.
            assert len(ops) <= 40
            assert sum(op.name.startswith('guard') for op in ops) <= 10
            assert not [op for op in ops if op.name.startswith('new')]
            assert not [op for op in ops if 'call' in op.name]
            targets = set(op.descr for op in trace.trace.operations if op.name == 'label')
            pending = [trace.trace]
            seen = set()
            while pending:
                part = pending.pop()
                if id(part) in seen:
                    continue
                seen.add(id(part))
                for op in part.operations:
                    bridge = getattr(op, 'bridge', None)
                    if bridge is None:
                        continue
                    pending.append(bridge)
                    if any(op.name == 'jump' and op.descr in targets
                           for op in bridge.operations):
                        continuing_bridges.append(bridge)
        assert continuing_bridges
        # Boxing the final return value is fine; continuing the search must
        # keep the indices unboxed even when the callback changes direction.
        for bridge in continuing_bridges:
            assert not [op for op in bridge.operations if op.name.startswith('new')]

    def test_bsearch_index_mutation(self, topaz, tmpdir):
        self.run(topaz, tmpdir, '''
        i = 0
        while i < 10000
          a = [0, 1, 2, 3, 4, 5, 6, 7]
          count = 0
          result = a.bsearch_index do |x|
            count += 1
            raise 'stale array element' unless x == (count == 1 ? 4 : nil)
            a.clear
            false
          end
          raise 'wrong bounds' unless count == 3 && result.nil?
          i += 1
        end
        ''')
