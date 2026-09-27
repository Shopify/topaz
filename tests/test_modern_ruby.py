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
