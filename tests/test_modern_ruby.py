"""Language features added between Ruby 2.4 and Ruby 4.0."""

from .base import BaseTopazTest


class TestLeadingOperators(BaseTopazTest):
    def test_leading_dot_after_comment_line(self, space):
        w_res = space.execute("""
        x = [3, 1, 2]
          # comment lines may sit between the lines of a chain
          .sort
          .map { |i| i * 2 }
        return x
        """)
        assert self.unwrap(space, w_res) == [2, 4, 6]

    def test_leading_logical_operators(self, space):
        # Ruby 4.0: a line starting with ||, &&, and or `or` continues the
        # previous line, with the usual precedence.
        w_res = space.execute("""
        a = nil
        b = 2
        x = a
          || b
        y = b
          # a comment
          && 3
        z = false
          or 4
        w = true
          and 5
        return [x, y, z, w]
        """)
        assert self.unwrap(space, w_res) == [2, 3, False, True]

    def test_leading_word_must_be_whole_word(self, space):
        w_res = space.execute("""
        def orange; :orange; end
        def android; :android; end
        x = 1
        orange
        y = 2
        return android
        """)
        assert self.unwrap(space, w_res) == "android"


class TestImmediates(BaseTopazTest):
    def test_immediates_are_frozen(self, space):
        w_res = space.execute("""
        return [nil, true, false, :sym, 1, 2 ** 70, 1.5].map(&:frozen?)
        """)
        assert self.unwrap(space, w_res) == [True] * 7

    def test_dup_and_clone_return_self(self, space):
        # Ruby 2.4
        w_res = space.execute("""
        objs = [nil, true, false, :sym, 1, 2 ** 70, 1.5]
        return objs.map { |o| o.dup.equal?(o) && o.clone.equal?(o) }
        """)
        assert self.unwrap(space, w_res) == [True] * 7


class TestPrismSyntax(BaseTopazTest):
    """Syntax the old parser could not handle, which Prism parses."""

    def test_it_block_parameter(self, space):
        # Ruby 3.4
        w_res = space.execute("return [1, 2].map { it * 2 }")
        assert self.unwrap(space, w_res) == [2, 4]

    def test_numbered_block_parameters(self, space):
        # Ruby 2.7
        w_res = space.execute("return [[1, 2], [3, 4]].map { _1 + _2 }")
        assert self.unwrap(space, w_res) == [3, 7]

    def test_endless_method(self, space):
        # Ruby 3.0
        w_res = space.execute("""
        def square(x) = x * x
        def five = 5
        return [square(3), five]
        """)
        assert self.unwrap(space, w_res) == [9, 5]

    def test_hash_shorthand(self, space):
        # Ruby 3.1
        w_res = space.execute("""
        x = 1
        def y = 2
        return {x:, y:}
        """)
        assert self.unwrap(space, w_res) == {"x": 1, "y": 2}

    def test_rescue_in_do_block(self, space):
        # Ruby 2.5
        w_res = space.execute("""
        return [1, 0].map do |d|
          10 / d
        rescue ZeroDivisionError
          :inf
        end
        """)
        assert self.unwrap(space, w_res) == [10, "inf"]

    def test_squiggly_heredoc(self, space):
        # Ruby 2.3
        w_res = space.execute("""
        return <<~EOS
          one
            two
        EOS
        """)
        assert self.unwrap(space, w_res) == "one\n  two\n"

    def test_safe_navigation(self, space):
        # Ruby 2.3
        w_res = space.execute("""
        calls = 0
        count = proc { calls += 1; nil }
        return [nil&.length, "ab"&.length, count.call&.length, calls]
        """)
        assert self.unwrap(space, w_res) == [None, 2, None, 1]

    def test_named_captures_assign_locals(self, space):
        w_res = space.execute("""
        if /(?<year>\\d+)-(?<month>\\d+)/ =~ "2025-12"
          a = [year, month]
        end
        /(?<nope>x)/ =~ "y"
        return [a, nope, $~]
        """)
        assert self.unwrap(space, w_res) == [["2025", "12"], None, None]

    def test_retry(self, space):
        w_res = space.execute("""
        tries = 0
        begin
          tries += 1
          raise "again" if tries < 3
        rescue
          retry
        end
        return tries
        """)
        assert self.unwrap(space, w_res) == 3

    def test_symbol_array(self, space):
        w_res = space.execute("return %i[a b]")
        assert self.unwrap(space, w_res) == ["a", "b"]


class TestNilEndedRanges(BaseTopazTest):
    """Endless (Ruby 2.6) and beginless (Ruby 2.7) ranges."""

    def test_indexing(self, space):
        w_res = space.execute("""
        a = [1, 2, 3, 4, 5]
        return [a[2..], a[..1], a[1...], "hello"[1..], "hello"[..-2]]
        """)
        assert self.unwrap(space, w_res) == [
            [3, 4, 5], [1, 2], [2, 3, 4, 5], "ello", "hell"]

    def test_iteration(self, space):
        w_res = space.execute("""
        seen = []
        (1..).each { |i| seen << i; break if i >= 3 }
        return [seen, (1..).first(2), (1..).step(3).first(3)]
        """)
        assert self.unwrap(space, w_res) == [[1, 2, 3], [1, 2], [1, 4, 7]]

    def test_membership(self, space):
        w_res = space.execute("""
        size = case 5 when (..3) then :small when (4..) then :large end
        return [(1..).include?(10 ** 6), (..5).cover?(6), (1...).include?(0),
                size]
        """)
        assert self.unwrap(space, w_res) == [True, False, False, "large"]

    def test_inspect_and_size(self, space):
        w_res = space.execute("""
        return [(1..).inspect, (..5).inspect, (nil..nil).inspect, (1..).size]
        """)
        [a, b, c, d] = self.unwrap(space, w_res)
        assert [a, b, c] == ["1..", "..5", "nil..nil"]
        assert d == float("inf")

    def test_errors(self, space):
        with self.raises(space, "RangeError", "cannot convert endless range to an array"):
            space.execute("(1..).to_a")
        with self.raises(space, "TypeError", "can't iterate from NilClass"):
            space.execute("(..1).each {}")

    def test_leading_range_is_not_a_line_continuation(self, space):
        w_res = space.execute("""
        x = 1
        ..2
        return x
        """)
        assert self.unwrap(space, w_res) == 1


class TestArgumentForwarding(BaseTopazTest):
    def test_forward_everything(self, space):
        # Ruby 2.7 (and leading arguments, 3.0)
        w_res = space.execute("""
        def target(*args, **kw, &blk)
          [args, kw, blk ? blk.call : nil]
        end
        def fwd(...) = target(...)
        def fwd_leading(a, ...) = target(a, 0, ...)
        return [fwd(1, 2, k: 3) { :b }, fwd_leading(1, 2)]
        """)
        assert self.unwrap(space, w_res) == [
            [[1, 2], {"k": 3}, "b"], [[1, 0, 2], {}, None]]

    def test_anonymous_parameters(self, space):
        # Ruby 3.1 (&) and 3.2 (* and **)
        w_res = space.execute("""
        def target(*args, **kw, &blk)
          [args, kw, blk ? blk.call : nil]
        end
        def rest(*) = target(*)
        def kws(**) = target(**)
        def blk(&) = target(&)
        return [rest(1, 2), kws(a: 1), blk { :x }]
        """)
        assert self.unwrap(space, w_res) == [
            [[1, 2], {}, None], [[], {"a": 1}, None], [[], {}, "x"]]

    def test_forward_to_super(self, space):
        w_res = space.execute("""
        class P; def m(*a, &b) = [a, b.call]; end
        class C < P; def m(...) = super(...); end
        return C.new.m(1) { 2 }
        """)
        assert self.unwrap(space, w_res) == [[1], 2]
