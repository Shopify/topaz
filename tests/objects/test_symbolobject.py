from ..base import BaseTopazTest


class TestSymbolObject(BaseTopazTest):
    def test_name(self, space):
        space.execute("Symbol")

    def test_symbol(self, space):
        w_res = space.execute("return :foo")
        assert space.symbol_w(w_res) == "foo"

    def test_to_s(self, space):
        w_res = space.execute("return :foo.to_s")
        assert space.str_w(w_res) == "foo"

    def test_inspect(self, space):
        w_res = space.execute("return :foo.inspect")
        assert space.str_w(w_res) == ":foo"

    def test_comparator_lt(self, space):
        w_res = space.execute("return :a <=> :b")
        assert space.int_w(w_res) == -1

    def test_comparator_eq(self, space):
        w_res = space.execute("return :a <=> :a")
        assert space.int_w(w_res) == 0

    def test_comparator_gt(self, space):
        w_res = space.execute("return :b <=> :a")
        assert space.int_w(w_res) == 1

    def test_comparator_non_symbol(self, space):
        w_res = space.execute("return :a <=> 12")
        assert w_res is space.w_nil

    def test_identity(self, space):
        w_res = space.execute("return [:x.object_id, :x.object_id]")
        id1, id2 = self.unwrap(space, w_res)
        assert id1 == id2

    def test_to_sym(self, space):
        w_res = space.execute("return :x, :x.to_sym")
        s1, s2 = self.unwrap(space, w_res)
        assert s1 == s2 == "x"

    def test_to_proc(self, space):
        w_res = space.execute("return :+.to_proc.call(2, 3)")
        assert space.int_w(w_res) == 5
        w_res = space.execute("""
        class SymProcTarget
          def blk; yield 2; end
          def many(*a) a end
        end
        pr = :many.to_proc
        return [pr.lambda?, pr.arity, pr.equal?(:many.to_proc), pr.equal?(:blk.to_proc),
                [SymProcTarget.new].map(&:many), [SymProcTarget.new].each_with_index.map(&:many),
                {a: 1}.map(&:first), (1..3).inject(&:+), [[1, 2]].map(&:first),
                :blk.to_proc.call(SymProcTarget.new) { |x| x + 1 },
                pr.call(SymProcTarget.new, *[7, 8])]
        """)
        assert self.unwrap(space, w_res) == [
            True, -2, True, False, [[]], [[0]], ["a"], 6, [1], 3, [7, 8]]
        with self.raises(space, "ArgumentError"):
            space.execute(":many.to_proc.call")
        with self.raises(space, "NoMethodError"):
            space.execute(":many.to_proc.call([1])")

    def test_succ(self, space):
        w_res = space.execute('return :abcd.succ')
        assert space.symbol_w(w_res) == "abce"
        w_res = space.execute('return :THX1138.succ')
        assert space.symbol_w(w_res) == "THX1139"
        w_res = space.execute('return :"<<koala>>".succ')
        assert space.symbol_w(w_res) == "<<koalb>>"
        w_res = space.execute('return :"ZZZ9999".succ')
        assert space.symbol_w(w_res) == "AAAA0000"
        w_res = space.execute('return :"***".succ')
        assert space.symbol_w(w_res) == "**+"
