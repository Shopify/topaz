"""Language features added between Ruby 2.4 and Ruby 4.0."""

import pytest

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


class TestInspect(BaseTopazTest):
    def test_string_inspect_escapes(self, space):
        w_res = space.execute(r"""
        return ['a"b', "a\\b", "\n\t\e\u0001", "\#{x}", "\u00e9", "\xff"].map(&:inspect)
        """)
        assert self.unwrap(space, w_res) == [
            r'"a\"b"', r'"a\\b"', r'"\n\t\e\u0001"', r'"\#{x}"',
            u'"\u00e9"'.encode("utf-8"), r'"\xFF"',
        ]

    def test_symbol_inspect(self, space):
        w_res = space.execute("""
        return [:foo_bar, :+, :a?, :a=, :[]=, :@iv, :$g, :"foo bar", :"9x"].map(&:inspect)
        """)
        assert self.unwrap(space, w_res) == [
            ":foo_bar", ":+", ":a?", ":a=", ":[]=", ":@iv", ":$g",
            ':"foo bar"', ':"9x"',
        ]

    def test_hash_inspect(self, space):
        # Ruby 3.4
        w_res = space.execute("""
        h = {a: 1, "b" => 2, 1 => 3, :+ => 4, :a? => 5, nil => 6}
        return h.inspect
        """)
        assert self.unwrap(space, w_res) == (
            '{a: 1, "b" => 2, 1 => 3, "+": 4, a?: 5, nil => 6}')


class TestPatternMatching(BaseTopazTest):
    """case/in, `=>` and `in` (Ruby 2.7/3.0)."""

    def test_case_in(self, space):
        w_res = space.execute("""
        def m(v)
          case v
          in Integer | Float => n if n > 100 then [:big, n]
          in Integer => n then [:int, n]
          in [] then :empty
          in [1, *rest] then [:one, rest]
          in [Integer => a, String => b] then [:pair, a, b]
          in [*, :needle, *post] then [:found, post]
          in {name: String => name, age: Integer => age} then [:person, name, age]
          in {type: :point, **rest} then [:point, rest]
          in {} then :empty_hash
          in nil then :nil
          in String if v.empty? then :empty_string
          in /\\A\\d+\\z/ then :digits
          in ^$pinned then :pinned
          else [:other, v]
          end
        end
        $pinned = "pin"
        return [150, 7, [], [1, 2, 3], [5, "x"], [0, :needle, 9, 8],
                {name: "Al", age: 3}, {type: :point, x: 1}, {}, nil, "",
                "123", "pin", :sym].map { |v| m(v) }
        """)
        assert self.unwrap(space, w_res) == [
            ["big", 150], ["int", 7], "empty", ["one", [2, 3]],
            ["pair", 5, "x"], ["found", [9, 8]], ["person", "Al", 3],
            ["point", {"x": 1}], "empty_hash", "nil", "empty_string",
            "digits", "pinned", ["other", "sym"],
        ]

    def test_rightward_and_in(self, space):
        w_res = space.execute("""
        [1, [2, 3]] => [a, [b, c]]
        return [a, b, c, (5 in Integer), ("s" in Integer)]
        """)
        assert self.unwrap(space, w_res) == [1, 2, 3, True, False]

    def test_no_match(self, space):
        with self.raises(space, "NoMatchingPatternError", "1: String === 1 does not return true"):
            space.execute("1 => String")
        with self.raises(space, "NoMatchingPatternError", "5: String === 5 does not return true"):
            space.execute("case 5; in String then 1; end")

    def test_deconstruct(self, space):
        w_res = space.execute("""
        Point = Struct.new(:x, :y)
        case Point.new(1, 2)
        in [x, y] then as_array = [x, y]
        end
        case Point.new(3, 4)
        in {x:, y:} then as_hash = [x, y]
        end
        exact = case {a: 1, b: 2}
                in {a: 1, **nil} then :exact
                in {a: 1} then :subset
                end
        return [as_array, as_hash, exact]
        """)
        assert self.unwrap(space, w_res) == [[1, 2], [3, 4], "subset"]


class TestCoreMethods(BaseTopazTest):
    """Core methods added between Ruby 2.2 and 4.0."""

    def test_kernel(self, space):
        w_res = space.execute("return [5.then { |x| x + 1 }, 3.itself]")
        assert self.unwrap(space, w_res) == [6, 3]

    def test_enumerable(self, space):
        w_res = space.execute("""
        return [[1, 2, 3].sum, [0.1, 0.2, 0.3].sum, (1..100).sum,
                [1, 2, 3].filter_map { |x| x * 2 if x.odd? },
                %w[a b a].tally, [[1, 2]].to_h, [1, 2].to_h { |x| [x, -x] },
                [1, 2, 4, 5].slice_when { |a, b| b != a + 1 }.to_a,
                [1, nil].compact]
        """)
        assert self.unwrap(space, w_res) == [
            6, 0.6, 5050, [2, 6], {"a": 2, "b": 1}, {1: 2}, {1: -1, 2: -2},
            [[1, 2], [4, 5]], [1]]

    def test_array(self, space):
        w_res = space.execute("""
        return [[1, 2].union([2, 3]), [1, 2, 3].difference([2]),
                [1, 2].intersection([2, 3]), [1, 2].intersect?([3]),
                [1, [2, [3]]].dig(1, 1, 0), [1, 2, 3, 4].rfind(&:odd?),
                [1, 3, 5, 7].bsearch { |x| x >= 4 }, [1].append(2)]
        """)
        assert self.unwrap(space, w_res) == [
            [1, 2, 3], [1, 3], [2], False, 3, 3, 5, [1, 2]]

    def test_hash(self, space):
        w_res = space.execute("""
        h = {a: 1, b: nil}
        return [h.transform_values(&:to_s), h.transform_keys(&:to_s),
                h.slice(:a), h.compact, {a: {b: 2}}.dig(:a, :b),
                h.except(:b), h.filter { |k, v| v }]
        """)
        assert self.unwrap(space, w_res) == [
            {"a": "1", "b": ""}, {"a": 1, "b": None}, {"a": 1}, {"a": 1},
            2, {"a": 1}, {"a": 1}]

    def test_string(self, space):
        w_res = space.execute("""
        return ["hello".match?(/ll/), "pre-x".delete_prefix("pre-"),
                "x.rb".delete_suffix(".rb"), "ABC".casecmp?("abc"),
                "aaabbb".squeeze, "0x1A".hex, "0b101".oct, (-"y").frozen?]
        """)
        assert self.unwrap(space, w_res) == [
            True, "x", "x", True, "ab", 26, 5, True]

    def test_numeric(self, space):
        w_res = space.execute("""
        return [1234.digits, 2.pow(100, 1000), 7.ceildiv(2), 12.gcd(18),
                Integer.sqrt(10 ** 20), 15.clamp(1, 10), 5.clamp(..3),
                1.23456.round(2), 1234.5.round(-2), Math.log1p(0.0)]
        """)
        assert self.unwrap(space, w_res) == [
            [4, 3, 2, 1], 376, 4, 6, 10 ** 10, 10, 3, 1.23, 1200, 0.0]

    def test_proc_composition(self, space):
        w_res = space.execute("""
        double = proc { |x| x * 2 }
        inc = ->(x) { x + 1 }
        add = ->(a, b) { a + b }
        return [(double >> inc).call(3), (double << inc).call(3),
                add.curry[1][2], 5.method(:+).curry[3]]
        """)
        assert self.unwrap(space, w_res) == [7, 8, 3, 8]


class TestImplicitSuper(BaseTopazTest):
    def test_passes_keywords_as_keywords(self, space):
        w_res = space.execute("""
        class P
          def m(a, b = 2, *r, k: 1, **o, &blk) = [a, b, r, k, o, blk && blk.call]
        end
        class C < P
          def m(a, b = 5, *r, k: 9, **o, &blk)
            [1].map { super }.first
          end
        end
        return [C.new.m(1), C.new.m(1, 2, 3, k: 4, z: 5) { :blk }]
        """)
        assert self.unwrap(space, w_res) == [
            [1, 5, [], 9, {}, None], [1, 2, [3], 4, {"z": 5}, "blk"]]


class TestData(BaseTopazTest):
    def test_define(self, space):
        # Ruby 3.2
        w_res = space.execute("""
        Point = Data.define(:x, :y) do
          def norm = x * x + y * y
        end
        a = Point.new(1, 2)
        b = Point.new(x: 1, y: 2)
        return [a.inspect, a == b, a.hash == b.hash, a.to_h, a.norm,
                a.frozen?, a.with(y: 5).inspect, Point[3, 4].x]
        """)
        assert self.unwrap(space, w_res) == [
            "#<data Point x=1, y=2>", True, True, {"x": 1, "y": 2}, 5, True,
            "#<data Point x=1, y=5>", 3]

    def test_errors_and_defaults(self, space):
        w_res = space.execute("""
        Point = Data.define(:x, :y)
        errors = []
        [[1], [1, 2, 3]].each do |args|
          begin
            Point.new(*args)
          rescue ArgumentError => e
            errors << e.message
          end
        end
        WithDefault = Data.define(:a) { def initialize(a: 0) = super }
        return [errors, WithDefault.new.a]
        """)
        assert self.unwrap(space, w_res) == [
            ["missing keyword: :y", "wrong number of arguments (given 3, expected 0..2)"],
            0]


class TestSetAndWarning(BaseTopazTest):
    def test_set_is_core(self, space):
        # Ruby 4.0: no require, and Set[...] inspection.
        w_res = space.execute("return [Set[1, 2, 2].size, Set[1, 2].inspect]")
        assert self.unwrap(space, w_res) == [2, "Set[1, 2]"]

    def test_warning(self, space):
        w_res = space.execute("""
        $VERBOSE = false
        seen = []
        Warning.define_singleton_method(:warn) { |message| seen << message }
        warn "one", "two"
        return [seen, Warning[:experimental], Warning.categories.include?(:deprecated)]
        """)
        assert self.unwrap(space, w_res) == [["one\ntwo\n"], True, True]


class TestKeywordArguments(BaseTopazTest):
    """Keyword argument separation (Ruby 3.0)."""

    def test_hash_argument_is_positional(self, space):
        w_res = space.execute("""
        def g(a, k: 1) = [a, k]
        def any(*args) = args
        return [g({k: 2}), g(1, k: 3), g(1, **{k: 4}), any(a: 1), any(**{})]
        """)
        assert self.unwrap(space, w_res) == [
            [{"k": 2}, 1], [1, 3], [1, 4], [{"a": 1}], []]

    def test_hash_does_not_become_keywords(self, space):
        with self.raises(space, "ArgumentError", "wrong number of arguments (given 2, expected 1)"):
            space.execute("def g(a, k: 1) = [a, k]; g(1, {k: 2})")
        with self.raises(space, "ArgumentError", "wrong number of arguments (given 1, expected 0)"):
            space.execute("def h(**kw) = kw; h({a: 1})")

    def test_ruby2_keywords_and_forwarding(self, space):
        w_res = space.execute("""
        class Target; def call(a, b: 0) = [a, b]; end
        class Proxy
          def initialize(t) = @t = t
          def method_missing(name, *args, &blk) = @t.send(name, *args, &blk)
          ruby2_keywords :method_missing
        end
        def g(a, k: 1) = [a, k]
        def fwd(...) = g(...)
        return [Proxy.new(Target.new).call(1, b: 2), fwd(5, k: 6), fwd({k: 7})]
        """)
        assert self.unwrap(space, w_res) == [[1, 2], [5, 6], [{"k": 7}, 1]]

    def test_blocks(self, space):
        w_res = space.execute("""
        blk = proc { |x, k: 0| [x, k] }
        return [blk.call(1, k: 2), blk.call({k: 3})]
        """)
        assert self.unwrap(space, w_res) == [[1, 2], [{"k": 3}, 0]]


class TestBreakAndLazy(BaseTopazTest):
    def test_break_through_a_captured_block(self, space):
        w_res = space.execute("""
        e = Enumerator.new { |y| y << 1; y << 2; y << 3 }
        def m(&b) = [b.call, :after]
        r = [e.each { |x| break x * 10 if x == 2 }, m { break :broke }]
        begin
          proc { break }.call
        rescue LocalJumpError
          r << :local_jump_error
        end
        return r
        """)
        assert self.unwrap(space, w_res) == [20, "broke", "local_jump_error"]

    def test_lazy(self, space):
        w_res = space.execute("""
        return [(1..Float::INFINITY).lazy.map { _1 * 2 }.select { _1 % 3 == 0 }.first(3),
                (1..).lazy.filter_map { _1 * 2 if _1.odd? }.take(3).to_a,
                (1..).lazy.take_while { _1 < 4 }.to_a,
                (1..).lazy.uniq { _1 % 3 }.first(3),
                Enumerator.produce(1) { _1 * 2 }.take(5)]
        """)
        assert self.unwrap(space, w_res) == [
            [6, 12, 18], [2, 6, 10], [1, 2, 3], [1, 2, 3], [1, 2, 4, 8, 16]]


class TestDefinitionValues(BaseTopazTest):
    def test_def_returns_the_method_name(self, space):
        w_res = space.execute("""
        a = def f = 1
        b = def self.g; end
        return [a, b]
        """)
        assert self.unwrap(space, w_res) == ["f", "g"]

    def test_attr_methods_return_names(self, space):
        w_res = space.execute("""
        class A
          R = [attr_reader(:a, :b), attr_writer(:c), attr_accessor(:d), attr(:e)]
        end
        return A::R
        """)
        assert self.unwrap(space, w_res) == [
            ["a", "b"], ["c="], ["d", "d="], ["e"]]

    def test_visibility_with_arrays_and_return_values(self, space):
        w_res = space.execute("""
        class A
          R1 = private(attr_reader :a, :b)
          R2 = private def f = 1
          R3 = private
          R4 = public(:f, "a")
          def g = 2
          public
        end
        return [A::R1, A::R2, A::R3, A::R4, A.private_instance_methods(false),
                A.public_method_defined?(:g), A.private_method_defined?(:g),
                A.private_method_defined?(:b), A.method_defined?(:b), A.method_defined?(:f),
                A.public_method_defined?(:to_s), A.public_method_defined?(:to_s, false)]
        """)
        assert self.unwrap(space, w_res) == [
            ["a", "b"], "f", None, ["f", "a"], ["b", "g"], False, True,
            True, False, True, True, False]

    def test_defined_on_undefined_receivers(self, space):
        w_res = space.execute("""
        @y = 1
        return [defined?(Undefined.foo), defined?(Undefined::X), defined?(Comparable::Undefined.x),
                defined?(@x.to_s), defined?($undefined.to_s), defined?(@y.to_s),
                defined?(String.new), defined?(nil.nil?), defined?(x.y)]
        """)
        assert self.unwrap(space, w_res) == [
            None, None, None, None, None, "method", "method", "method", None]


class TestEnvironmentModules(BaseTopazTest):
    def test_rbconfig(self, space):
        w_res = space.execute("""
        require "rbconfig"
        c = RbConfig::CONFIG
        return [RbConfig.ruby.end_with?("/bin/topaz"), c["ruby_version"], c["MAJOR"],
                c["host_os"], c["DLEXT"], c["rubylibdir"].end_with?("lib-ruby")]
        """)
        assert self.unwrap(space, w_res) == [True, "4.0.0", "4", "linux", "so", True]

    def test_env_merge_and_to_h(self, space):
        w_res = space.execute("""
        ENV["TOPAZ_TEST_A"] = "1"
        ENV.merge!({"TOPAZ_TEST_A" => nil, "TOPAZ_TEST_B" => "2"})
        r = [ENV["TOPAZ_TEST_A"], ENV["TOPAZ_TEST_B"], ENV.to_h.class, ENV.to_h["TOPAZ_TEST_B"]]
        ENV.delete("TOPAZ_TEST_B")
        return r
        """)
        assert self.unwrap(space, w_res) == [None, "2", space.w_hash, "2"]

    def test_gc(self, space):
        w_res = space.execute("""
        return [GC.start, GC.count, GC.stat[:count], GC.stat(:count), GC.disable,
                GC.respond_to?(:auto_compact)]
        """)
        assert self.unwrap(space, w_res) == [None, 0, 0, 0, False, False]


class TestRegexpEscapes(BaseTopazTest):
    def test_numeric_escapes(self, space):
        w_res = space.execute("""
        return ["ab\\0cd" =~ /\\0/, "a\\nb" =~ /\\012/, "abab" =~ /(ab)\\1/,
                "xAa" =~ /(a)\\1/i, "x\\x01y" =~ /[\\1]/, "'hi'" =~ /(['"])hi\\1/]
        """)
        assert self.unwrap(space, w_res) == [2, 1, 0, 1, 1, 0]

    def test_lookaround_in_alternation(self, space):
        # From ActiveSupport::Inflector#underscore; used to crash the
        # regexp optimizer.
        w_res = space.execute("""
        return ["HTMLParser".gsub(/(?<=[A-Z])(?=[A-Z][a-z])|(?<=[a-z\\d])(?=[A-Z])/, "_"),
                "abc" =~ /a(?=.c)|a(?=.d)/, "aab" =~ /a(?!.b)|ab/]
        """)
        assert self.unwrap(space, w_res) == ["HTML_Parser", 0, 1]

    def test_alternation(self, space):
        # Branches used to lose their first item to a bogus common prefix.
        w_res = space.execute("""
        return ["cd" =~ /ab|cd/, "xcd" =~ /ab|cd/, "ad" =~ /ab|cd/, "far" =~ /foo|far/,
                "by" =~ /[a-c]x|by/, "mnop" =~ /mnq|mno/, "ac" =~ /(a)b|(a)c/, $~[2]]
        """)
        assert self.unwrap(space, w_res) == [0, 1, None, 0, 0, 0, 0, "a"]


class TestGsubAndScan(BaseTopazTest):
    def test_empty_matches(self, space):
        w_res = space.execute("""
        return ["abc".gsub(//, "-"), "abc".gsub(/(?=b)/, "_"), "abc".scan(/(?=b)/),
                "abc".scan(/b|/), "abc".gsub("", "-"), "abc".gsub(/$/, "!"),
                "h\xC3\xA9".gsub(//, ".")]
        """)
        assert self.unwrap(space, w_res) == [
            "-a-b-c-", "a_bc", [""], ["", "b", "", ""], "-a-b-c-", "abc!",
            ".h.\xc3\xa9."]

    def test_replacements_and_last_match(self, space):
        w_res = space.execute("""
        r = ["a1b2".gsub(/(\d)/) { $1 * 2 }, "a1b2".gsub(/(?<d>\d)/, '<\\k<d>>'),
             "hello".gsub(/l(l)?/, '[\\0|\\1|\\&]'), "hello".sub(/ll/, '<\\`>'),
             "abcabc".gsub("c", "!"), "a-b_c".gsub(/[-_]/, "-" => "+", "_" => "=")]
        "abc".gsub(/q/, "")
        r << $~
        "abc".gsub(/b/, "")
        r << $~[0] << "abc".match(/a/).pre_match
        return r
        """)
        assert self.unwrap(space, w_res) == [
            "a11b22", "a<1>b<2>", "he[ll|l|ll]o", "he<he>o", "ab!ab!", "a+b=c",
            None, "b", ""]


class TestErrinfo(BaseTopazTest):
    def test_errinfo_is_set_and_restored(self, space):
        w_res = space.execute("""
        r = []
        r << (raise "x" rescue $!.message)
        r << $!
        begin
          raise "a"
        rescue
          begin
            raise "b"
          rescue
            r << $!.message
          end
          r << $!.message
        end
        r << $!
        begin
          begin
            raise "c"
          rescue
            begin; raise "d"; rescue; end
            raise
          end
        rescue => e
          r << e.message
        end
        return r
        """)
        assert self.unwrap(space, w_res) == ["x", None, "b", "a", None, "c"]

    def test_return_from_rescue_restores_errinfo(self, space):
        # Kernel#caller rescues its own exception and returns from the
        # rescue clause; a bare raise after calling it must still re-raise
        # the exception being handled.
        w_res = space.execute("""
        def c
          begin
            raise "inner"
          rescue => e
            return e.message
          end
        end
        r = []
        begin
          raise LoadError, "outer"
        rescue LoadError
          r << c
          begin
            raise
          rescue LoadError => e2
            r << e2.message
          end
        end
        r << $!
        return r
        """)
        assert self.unwrap(space, w_res) == ["inner", "outer", None]

    def test_cause(self, space):
        w_res = space.execute("""
        r = []
        begin
          begin
            raise "a"
          rescue
            raise "b"
          end
        rescue => e
          r << e.cause.message << e.cause.cause
        end
        begin
          begin
            raise "a"
          rescue
            raise TypeError, "t", cause: nil
          end
        rescue => e
          r << e.cause
        end
        begin
          raise IOError, "bt", ["x.rb:1"]
        rescue => e
          r << e.backtrace
        end
        return r
        """)
        assert self.unwrap(space, w_res) == ["a", None, None, ["x.rb:1"]]


class TestRequire(BaseTopazTest):
    def test_circular_require_and_load_error(self, space, tmpdir):
        a = tmpdir.join("circ_a.rb")
        b = tmpdir.join("circ_b.rb")
        a.write("$circ << :a\nrequire %r\n" % str(b))
        b.write("$circ << :b\n$circ << require(%r)\n" % str(a))
        w_res = space.execute("""
        $circ = []
        require %r
        begin
          require "does/not/exist"
        rescue LoadError => e
          $circ << e.path << e.message
        end
        return $circ
        """ % str(a))
        assert self.unwrap(space, w_res) == [
            "a", "b", False, "does/not/exist",
            "cannot load such file -- does/not/exist"]


class TestSystem(BaseTopazTest):
    def test_system(self, space):
        w_res = space.execute("""
        return [system("true"), system("exit 3"), $?.exitstatus,
                system({"TOPAZ_X" => "y"}, 'test "$TOPAZ_X" = y')]
        """)
        assert self.unwrap(space, w_res) == [True, False, 3, True]


class TestIntegerBits(BaseTopazTest):
    def test_bignum_bit_operations(self, space):
        w_res = space.execute("""
        big = 2 ** 70
        return [big >> 68, big[70], big[3], (~big) + big, big.bit_length, 255.bit_length,
                (-1).bit_length, (-1)[100], ((big & 5).class == Integer), (big >> 69) + 1]
        """)
        assert self.unwrap(space, w_res) == [4, 1, 0, -1, 71, 8, 0, 1, True, 3]


class TestPack(BaseTopazTest):
    def test_pack(self, space):
        w_res = space.execute("""
        return [[1, 2].pack("C*"), [1].pack("N"), [-2].pack("s>"), ["abc"].pack("m0"),
                ["abc"].pack("m"), ["4a6f"].pack("H*"), [0x263a].pack("U"), [300].pack("w"),
                ["ab"].pack("A4"), ["1011"].pack("B*")]
        """)
        assert self.unwrap(space, w_res) == [
            "\x01\x02", "\x00\x00\x00\x01", "\xff\xfe", "YWJj", "YWJj\n", "Jo",
            "\xe2\x98\xba", "\x82\x2c", "ab  ", "\xb0"]

    def test_unpack(self, space):
        w_res = space.execute("""
        return ["\\x01\\x02".unpack("C*"), "\\xff\\xfe".unpack("s>"), "YWJj".unpack1("m0"),
                "Jo".unpack1("H*"), "\\xe2\\x98\\xba".unpack("U*"), "ab  ".unpack1("A*"),
                "\\x00\\x00\\x00\\x00\\x00\\x00\\xf8\\x3f".unpack1("E"), "abc".unpack("N"),
                "\\x01\\x02".unpack1("C", offset: 1)]
        """)
        assert self.unwrap(space, w_res) == [
            [1, 2], [-2], "abc", "4a6f", [0x263a], "ab", 1.5, [None], 2]

    def test_errors(self, space):
        with self.raises(space, "ArgumentError", "invalid base64"):
            space.execute('"!!!!".unpack1("m0")')
        with self.raises(space, "ArgumentError", "unknown unpack directive 'y' in 'y'"):
            space.execute('"x".unpack("y")')


class TestThreads(BaseTopazTest):
    def test_deferred_threads(self, space):
        w_res = space.execute("""
        r = []
        t = Thread.new(2) { |x| r << :ran; x * 21 }
        r << t.alive?
        r << t.value
        r << t.alive?
        never = Thread.new { loop { sleep 1 } }
        r << never.alive?
        failing = Thread.new { raise "boom" }
        begin
          failing.join
        rescue => e
          r << e.message
        end
        return r
        """)
        assert self.unwrap(space, w_res) == [True, "ran", 42, False, True, "boom"]

    def test_mutex_queue_condition_variable(self, space):
        w_res = space.execute("""
        m = Mutex.new
        r = [m.synchronize { m.locked? }, m.locked?, m.try_lock, m.try_lock]
        m.unlock
        q = Queue.new
        q << 1 << 2
        r << q.pop << q.size
        begin
          Queue.new.pop(true)
        rescue ThreadError => e
          r << e.message
        end
        cv = ConditionVariable.new
        r << cv.signal.equal?(cv)
        r << (Thread::Mutex.equal?(Mutex))
        return r
        """)
        assert self.unwrap(space, w_res) == [
            True, False, True, False, 1, 1, "queue empty", True, True]

    def test_weak_map(self, space):
        w_res = space.execute("""
        m = ObjectSpace::WeakMap.new
        k = "key"
        m[k] = 1
        return [m[k], m.key?(k), m.key?("key".dup), m.size]
        """)
        assert self.unwrap(space, w_res) == [1, True, False, 1]


class TestSecureRandomSupport(BaseTopazTest):
    def test_random_bytes_and_formatter(self, space):
        w_res = space.execute("""
        f = Object.new
        def f.bytes(n) = "\\x01" * n
        f.extend(Random::Formatter)
        return [Random.urandom(8).bytesize, Random.bytes(3).bytesize, Random.new_seed.class,
                f.random_number(1000).class, f.random_number.class, f.rand(3..3)]
        """)
        assert self.unwrap(space, w_res) == [8, 3, space.w_integer, space.w_integer, space.w_float, 3]


class TestRegexpFlags(BaseTopazTest):
    def test_inline_flags_and_case_folding(self, space):
        w_res = space.execute("""
        return ["A" =~ /(?i:a)/, "A" =~ /(?i)a/, "a" =~ /(?-mix:a)/, "AB" =~ /(?i-mx:a)b/,
                "a\\nb" =~ /(?m:a.b)/, "ab" =~ /(?x: a b )/, "ab" =~ /a(?#comment)b/,
                "x" =~ /X/i, "x" =~ /[X]/i, "Q" =~ /[a-z]/i, "q" =~ /[A-Z]/i, "Z" =~ /[^a-z]/i,
                "x" =~ /(?i:X)|y/]
        """)
        assert self.unwrap(space, w_res) == [0, 0, 0, None, 0, 0, 0, 0, 0, 0, 0, None, 0]

    def test_union_and_inspect(self, space):
        w_res = space.execute("""
        return [Regexp.union("a.b", /c/i).source, Regexp.union.source, Regexp.union(["x", "y"]).source,
                "c" =~ Regexp.union("a.b", /C/i), /x/mi.inspect, %r{a/b}.inspect]
        """)
        assert self.unwrap(space, w_res) == [
            "a\\.b|(?i-mx:c)", "(?!)", "x|y", 0, "/x/mi", "/a\\/b/"]


class TestEncodings(BaseTopazTest):
    def test_encoding_objects(self, space):
        w_res = space.execute("""
        return [Encoding::UTF_8.name, Encoding::BINARY.equal?(Encoding::ASCII_8BIT),
                Encoding::BINARY.inspect, Encoding.find("utf-8").name, __ENCODING__.name,
                (Encoding.find("nope") rescue $!.message), Encoding::US_ASCII.names]
        """)
        assert self.unwrap(space, w_res) == [
            "UTF-8", True, "#<Encoding:BINARY (ASCII-8BIT)>", "UTF-8", "UTF-8",
            "unknown encoding name - nope", ["US-ASCII", "ASCII", "ANSI_X3.4-1968", "646"]]

    def test_string_encoding_methods(self, space):
        w_res = space.execute("""
        return ["x".encoding.name, "x".b.encoding.name, "x".force_encoding("ASCII-8BIT").encoding.name,
                "\\xff".valid_encoding?, "\\xc3\\xa9".valid_encoding?, "\\xff".b.valid_encoding?,
                "\\xffa".scrub("?"), "abc".ascii_only?, "\\xc3\\xa9".ascii_only?,
                "\\xc3\\xa9".encode("US-ASCII", undef: :replace),
                ("\\xc3\\xa9".encode("US-ASCII") rescue $!.class.name),
                "\\xe9".force_encoding("ISO-8859-1").encode("UTF-8").bytes,
                "a<b>".encode(xml: :text), "x".encode("UTF-8").equal?(nil)]
        """)
        assert self.unwrap(space, w_res) == [
            "UTF-8", "ASCII-8BIT", "ASCII-8BIT", False, True, True, "?a", True, False,
            "?", "Encoding::UndefinedConversionError", [0xc3, 0xa9], "a&lt;b&gt;", False]


class TestPrepend(BaseTopazTest):
    def test_prepend_and_super(self, space):
        w_res = space.execute("""
        r = []
        module M; def foo = "M" + super; end
        class A; def foo = "A"; end
        class B < A; include M; end
        r << B.new.foo
        module P; def bar = "P(" + super + ")"; end
        class C; prepend P; def bar = "C"; end
        r << C.new.bar << C.ancestors.take(2).map(&:name) << C.new.is_a?(P)
        module Hook
          def self.prepended(base) = (@bases ||= []) << base.name
          def self.bases = @bases
          def self.prepend_features(base)
            base.instance_variable_set(:@seen, true)
            super
          end
        end
        class D; prepend Hook; end
        r << Hook.bases << D.instance_variable_get(:@seen)
        o = Object.new
        def o.x = "sx"
        module Ext; def x = "ext:" + super; end
        o.singleton_class.prepend(Ext)
        r << o.x
        return r
        """)
        assert self.unwrap(space, w_res) == [
            "MA", "P(C)", ["P", "C"], True, ["D"], True, "ext:sx"]


class TestReflection(BaseTopazTest):
    def test_instance_and_class_variables(self, space):
        w_res = space.execute("""
        o = Object.new
        o.instance_variable_set(:@a, 1)
        o.instance_variable_set(:@b, "x")
        r = [o.instance_variables, o.remove_instance_variable(:@b), o.instance_variables,
             (o.remove_instance_variable(:@z) rescue $!.message)]
        class K; @@v = 1; @i = 2; end
        class L < K; end
        r << L.class_variables << K.instance_variables << K.subclasses.map(&:name) << L.singleton_class.singleton_class?
        return r
        """)
        assert self.unwrap(space, w_res) == [
            ["@a", "@b"], "x", ["@a"], "instance variable @z not defined",
            ["@@v"], ["@i"], ["L"], True]

    def test_respond_to_respects_visibility(self, space):
        w_res = space.execute("""
        class A; def a = 1; private def b = 2; protected def c = 3; end
        x = A.new
        return [x.respond_to?(:a), x.respond_to?(:b), x.respond_to?(:b, true), x.respond_to?(:c),
                1.respond_to?(:puts), 1.public_send(:+, 2), (1.public_send(:puts) rescue $!.class.name)]
        """)
        assert self.unwrap(space, w_res) == [True, False, True, False, False, 3, "NoMethodError"]

    def test_empty_keyword_splat_passes_nothing(self, space):
        w_res = space.execute("""
        opts = {}
        return [[1, 2].push(**opts), 5.fdiv(2, **opts), "ab".upcase(**{})]
        """)
        assert self.unwrap(space, w_res) == [[1, 2], 2.5, "AB"]


class TestStringSearch(BaseTopazTest):
    def test_index_and_rindex(self, space):
        w_res = space.execute("""
        return ["hello".index("l"), "hello".index("z"), "hello".index("l", -2), "hello".index("", 5),
                "hello".index(/l+/), $~[0], "hello".rindex("l"), "hello".rindex("l", 2),
                "hello".rindex(/l/, 2), "hello".rindex(""), "a\\nb".lines, "ab".chars]
        """)
        assert self.unwrap(space, w_res) == [
            2, None, 3, 5, 2, "ll", 3, 2, 2, 5, ["a\n", "b"], ["a", "b"]]


class TestModernCoreMethods(BaseTopazTest):
    def test_integer_to_s_base_and_exception_inspect(self, space):
        w_res = space.execute("""
        return [255.to_s(16), (2 ** 70).to_s(16), -255.to_s(2), (5.to_s(1) rescue $!.message),
                RuntimeError.new("x").inspect, RuntimeError.new.inspect, RuntimeError.new("").inspect]
        """)
        assert self.unwrap(space, w_res) == [
            "ff", "400000000000000000", "-11111111", "invalid radix 1",
            "#<RuntimeError: x>", "#<RuntimeError: RuntimeError>", "RuntimeError"]

    def test_string_and_enumerable_methods(self, space):
        w_res = space.execute("""
        return ["  hi ".lstrip, "ab".center(6, "*"), "a-b-c".partition("-"), "a-b-c".rpartition("-"),
                "hello".delete("l"), "hello".count("lo"), "hello".delete("a-k"), "abc".gsub!(/z/, ""),
                [1, 5, 9].grep_v(5), [1, 2, 3, 4].slice_after(&:even?).to_a, [1, 3, 5, 7].bsearch_index { |x| x >= 4 },
                {a: 1} <= {a: 1, b: 2}, nil.to_h, 7.remainder(-3), 1.step(10, 4).to_a,
                :abc.match?(/b/), "ab".match(/(?<x>a)(?<y>b)/).named_captures]
        """)
        assert self.unwrap(space, w_res) == [
            "hi ", "**ab**", ["a", "-", "b-c"], ["a-b", "-", "c"], "heo", 3, "llo", None,
            [1, 9], [[1, 2], [3, 4]], 2, True, {}, 1, [1, 5, 9], True, {"x": "a", "y": "b"}]


class TestConstantsAndClassVariables(BaseTopazTest):
    def test_or_assign_undefined(self, space):
        w_res = space.execute("""
        class A
          def self.lp = (@@lp ||= [])
        end
        A.lp << 1
        X1 ||= 5
        X1 ||= 6
        module M; Y1 ||= 7; end
        M::Z1 ||= 8
        return [A.lp, X1, M::Y1, M::Z1]
        """)
        assert self.unwrap(space, w_res) == [[1], 5, 7, 8]

    def test_scoped_lookup_skips_toplevel(self, space):
        w_res = space.execute("""
        module Y2; end
        class K2; end
        class L2 < K2; Q = 1; end
        class L3 < L2; end
        return [(Y2::String rescue $!.class), (K2::String rescue $!.class), L3::Q, Object::String,
                (5::X rescue $!.class)]
        """)
        assert self.unwrap(space, w_res) == [
            space.w_NameError, space.w_NameError, 1, space.w_string, space.w_TypeError]


class TestTrAndFrozen(BaseTopazTest):
    def test_tr(self, space):
        w_res = space.execute("""
        s = "hello"
        unchanged = s.tr!("z", "y")
        return ["hello".tr("el", ""), "hello".tr("a-y", "b-z"), "hello".tr("^l", "*"),
                "hello".tr("lo", "x"), "hello".tr_s("l", "r"), "he-llo".tr("-", "_"),
                unchanged, s.upcase, "aabbcc".tr_s("a-c", "x")]
        """)
        assert self.unwrap(space, w_res) == [
            "ho", "ifmmp", "**ll*", "hexxx", "hero", "he_llo", None, "HELLO", "x"]

    def test_frozen_error(self, space):
        w_res = space.execute("""
        s = "ABC".freeze
        r = [(s.upcase! rescue [$!.class.name, $!.message, $!.receiver.equal?(s)])]
        r << ([1].freeze << 2 rescue $!.class.name)
        r << (FrozenError < RuntimeError)
        return r
        """)
        assert self.unwrap(space, w_res) == [
            ["FrozenError", 'can\'t modify frozen String: "ABC"', True], "FrozenError", True]


class TestFilesAndFibers(BaseTopazTest):
    def test_file_new_with_fd_and_options(self, space, tmpdir):
        path = str(tmpdir.join("f.txt"))
        w_res = space.execute("""
        File.write(%r, "hello")
        f = File.open(%r)
        g = File.new(f.fileno, autoclose: false, path: "x")
        r = [g.path, g.read(3), File.new(%r, mode: "r").read]
        File.open(%r, File::WRONLY | File::APPEND) { |x| x.write("!") }
        r << File.read(%r) << $stderr.sync << File.fnmatch("*.rb", "a.rb") << File.fnmatch("*", ".x")
        return r
        """ % (path, path, path, path, path))
        assert self.unwrap(space, w_res) == ["x", "hel", "hello", "hello!", True, True, False]

    def test_fiber_storage(self, space):
        w_res = space.execute("""
        Fiber[:a] = 1
        return [Fiber[:a], Fiber[:b], Fiber.current.class]
        """)
        assert self.unwrap(space, w_res) == [1, None, space.find_const(space.w_object, "Fiber")]


class TestModuleCopies(BaseTopazTest):
    def test_dup_and_extend(self, space):
        w_res = space.execute("""
        k = Kernel.dup
        k.class_eval { undef_method :to_s }
        m = Module.new { def foo = 1 }
        module A1; def a = 1; end
        module B1; def b = 2; end
        o = Object.new
        r = o.extend(A1, B1)
        return [k.method_defined?(:inspect), k.method_defined?(:to_s), Kernel.method_defined?(:to_s),
                m.dup.instance_methods(false), r.equal?(o), o.a + o.b]
        """)
        assert self.unwrap(space, w_res) == [True, False, True, ["foo"], True, 3]


class TestRegexpClasses(BaseTopazTest):
    def test_negated_single_characters(self, space):
        # [^x] used to compile to a plain x.
        w_res = space.execute("""
        return ["ab".match(/[^x]*/)[0], "ab" =~ /[^"]*$/, "X" =~ /[^x]/i, "ab" =~ /a[^b]|ab/,
                "q" =~ /[^ab]|x/, "a" =~ /[^ab]|x/]
        """)
        assert self.unwrap(space, w_res) == ["ab", 0, None, 0, 0, None]

    def test_posix_classes_and_extended_comments(self, space):
        w_res = space.execute("""
        return ["a" =~ /^[^[:word:]][^"]*$/, "-a" =~ /^[^[:word:]][^"]*$/, "_" =~ /[[:word:]]/,
                "_" =~ /[[:alnum:]]/, "`" =~ /[[:punct:]]/, "\\t" =~ /[[:cntrl:]]/, " " =~ /[[:graph:]]/,
                "1.5" =~ /^(?:[-+]?([0-9][0-9_,]*)?\\.[0-9]*(?# base 10))$/x]
        """)
        assert self.unwrap(space, w_res) == [None, 0, 0, None, 0, 0, None, 0]


    def test_hex_unicode_and_control_escapes(self, space):
        w_res = space.execute("""
        return [/[\\x01-\\x03]/.match("a\\x02")&.begin(0), /\\x41/.match("zA")&.begin(0),
                /[^"\\\\\\x00-\\x1f]*/n.match("abc\\"")[0], /\\u{41}\\cA/.match("xA\\x01")&.begin(0),
                /\\e/.match("a\\e")&.begin(0), /\\u00e9/.match("caf\\u00e9")&.begin(0)]
        """)
        assert self.unwrap(space, w_res) == [1, 1, "abc", 1, 1, 3]

    def test_sets_with_characters_beyond_ascii(self, space):
        w_res = space.execute("""
        p1 = /[\\/"\\\\\\x0-\\x1f\\u2028-\\u2029]/
        p3 = /[^\\u00e9a]+/
        p4 = /[\\u00e0-\\u00ff]+/
        return [p1.match("ab\\u2029c")&.begin(0), p1.match("abc"), p3.match("bc\\u00e9")&.[](0),
                p4.match("x\\u00e0\\u00e9\\u00ffz")&.[](0) == "\\u00e0\\u00e9\\u00ff", p4.match("x\\u0101"),
                "a\\u2028b".gsub(/[\\u2028\\u2029]/, "!"), p3.match("\\u00e9\\u00e9")]
        """)
        assert self.unwrap(space, w_res) == [2, None, "bc", True, None, "a!b", None]


class TestNumbers(BaseTopazTest):
    def test_float_to_s(self, space):
        w_res = space.execute("""
        return [22.0 / 7, 0.1 + 0.2, 1e20, 1.0e-5, 1e15, 1e14, 0.0001, -0.0, 5e-324, 2.5].map(&:to_s)
        """)
        assert self.unwrap(space, w_res) == [
            "3.142857142857143", "0.30000000000000004", "1.0e+20", "1.0e-05", "1.0e+15",
            "100000000000000.0", "0.0001", "-0.0", "5.0e-324", "2.5"]

    def test_integer_power_divmod_and_coercion(self, space):
        w_res = space.execute("""
        return [10 ** 0, (2 ** -2).inspect, 7.divmod(2), -7.divmod(2), (1 + Rational(1, 2)).inspect,
                (3 < Rational(7, 2)), 1.coerce(2.5), 2.0 == 2, (1 + "x" rescue $!.message),
                (1 < "x" rescue $!.message)]
        """)
        assert self.unwrap(space, w_res) == [
            1, "(1/4)", [3, 1], [-4, 1], "(3/2)", True, [2.5, 1.0], True,
            "String can't be coerced into Integer", "comparison of Integer with String failed"]

    def test_rational(self, space):
        w_res = space.execute("""
        return [Rational(1, 3) + Rational(1, 6), Rational(7, 2).round, Rational(-7, 2).round,
                Rational(5, 2).round(half: :even), Rational(1, 3).round(2), 0.75.to_r,
                Rational("1/3"), 0.333.rationalize, Rational(7, 3).divmod(Rational(1, 2)),
                1/2r].map(&:inspect)
        """)
        assert self.unwrap(space, w_res) == [
            "(1/2)", "4", "-4", "2", "(33/100)", "(3/4)", "(1/3)", "(333/1000)",
            "[4, (1/3)]", "(1/2)"]

    def test_format(self, space):
        w_res = space.execute("""
        return [format("%5d|%-5d|%05d|%+d|%.3d|%x|%#X|%o|%b|%08.3f|%e|%g|%-6s|%.2s|%p|%c|%%",
                       42, 42, 42, 42, 7, 255, 255, 8, 5, 3.14159, 12345.678, 0.0001234, "hi",
                       "hello", nil, 65),
                format("%x|%o", -255, -8), format("%<a>s-%<b>05.1f", a: "x", b: 2.25),
                format("%{a}/%{b}", a: 1, b: 2), format("%*d", 5, 1), format("%2$s %1$s", "a", "b"),
                "%.2f" % 2.675, "%.1f" % 0.05, "%.1f" % 0.25, "%.20f" % 2.675, "%s and %s" % ["a", "b"]]
        """)
        assert self.unwrap(space, w_res) == [
            "   42|42   |00042|+42|007|ff|0XFF|10|101|0003.142|1.234568e+04|0.0001234|hi    |he|nil|A|%",
            "..f01|..70", "x-002.2", "1/2", "    1", "b a", "2.68", "0.1", "0.2",
            "2.67499999999999982236", "a and b"]


class TestTimeAndDate(BaseTopazTest):
    def test_time(self, space):
        w_res = space.execute("""
        t = Time.utc(2024, 3, 5, 14, 7, 9)
        l = Time.new(2024, 1, 31, 23, 59, 59, "+09:00")
        return [t.year, t.month, t.day, t.hour, t.min, t.sec, t.wday, t.yday, t.to_i, t.to_s,
                Time.at(1700000000.5).utc.inspect, l.to_s, l.utc_offset, l.utc.to_s,
                t.strftime("%Y-%m-%dT%H:%M:%S%z %A %j %U %W %G-%V %e %l %P %L"), t.iso8601,
                Time.at(0).utc.iso8601(3), (t + 86400).day, t - Time.utc(2024, 3, 4),
                Time.utc(2021, 1, 1).strftime("%G %V %u")]
        """)
        assert self.unwrap(space, w_res) == [
            2024, 3, 5, 14, 7, 9, 2, 65, 1709647629, "2024-03-05 14:07:09 UTC",
            "2023-11-14 22:13:20.5 UTC", "2024-01-31 23:59:59 +0900", 32400,
            "2024-01-31 14:59:59 UTC",
            "2024-03-05T14:07:09+0000 Tuesday 065 09 10 2024-10  5  2 pm 000",
            "2024-03-05T14:07:09Z", "1970-01-01T00:00:00.000Z", 6, 137229.0, "2020 53 5"]

    def test_date(self, space):
        # Date comes from lib-ruby/ext/date_core.rb, which stands in for
        # CRuby's date_core extension.
        w_res = space.execute("""
        require "date"
        d = Date.new(2024, 2, 29)
        return [$LOADED_FEATURES.any? { |f| f.end_with?("ext/date_core.rb") }, d.to_s, d.wday, d.yday, d.jd, d.cweek, d.leap?, (d + 1).to_s, (d >> 12).to_s,
                (d - Date.new(2024, 1, 1)).inspect, d.strftime("%a %b %e %-m"),
                Date.new(2024, -1, -1).to_s, Date.valid_date?(2023, 2, 29), Date.jd(2460000).to_s,
                Date.commercial(2024, 1, 1).to_s, Date.parse("March 5, 2024").to_s,
                Date.strptime("03/05/2024", "%m/%d/%Y").to_s, (Date.new(1582, 10, 15) - 1).to_s,
                Date.new(2024, 3, 5).httpdate]
        """)
        assert self.unwrap(space, w_res) == [
            True, "2024-02-29", 4, 60, 2460370, 9, True, "2024-03-01", "2025-02-28", "(59/1)",
            "Thu Feb 29 2", "2024-12-31", False, "2023-02-24", "2024-01-01", "2024-03-05",
            "2024-03-05", "1582-10-04", "Tue, 05 Mar 2024 00:00:00 GMT"]

    def test_datetime(self, space):
        w_res = space.execute("""
        require "date"
        dt = DateTime.new(2024, 3, 5, 10, 20, 30, "+09:00")
        return [dt.to_s, dt.hour, dt.offset.inspect, dt.new_offset(0).to_s,
                (dt + Rational(1, 2)).to_s, dt.to_time.utc.to_s,
                DateTime.parse("2024-03-05T10:20:30Z").to_s,
                Time.utc(2024, 3, 5, 1, 2, 3).to_datetime.to_s]
        """)
        assert self.unwrap(space, w_res) == [
            "2024-03-05T10:20:30+09:00", 10, "(3/8)", "2024-03-05T01:20:30+00:00",
            "2024-03-05T22:20:30+09:00", "2024-03-05 01:20:30 UTC", "2024-03-05T10:20:30+00:00",
            "2024-03-05T01:02:03+00:00"]


class TestMethodVisibilityAndEval(BaseTopazTest):
    def test_module_function_and_inherited_visibility(self, space):
        w_res = space.execute("""
        module M1; module_function; def f = 1; end
        class A1; def pub = 1; end
        class B1 < A1; private :pub; end
        return [M1.f, M1.respond_to?(:f), M1.private_instance_methods(false),
                A1.new.respond_to?(:pub), B1.new.respond_to?(:pub)]
        """)
        assert self.unwrap(space, w_res) == [1, True, ["f"], True, False]

    def test_eval_bindings(self, space):
        w_res = space.execute("""
        t = 5
        r = []
        [1].each { |e| r << eval("t") }
        x = 7
        [2].each { |q| y = 3; r << eval("[q, y, x, t]") }
        b = binding
        b.local_variable_set(:x, 8)
        r << b.local_variable_get(:x) << x << b.local_variable_defined?(:zz)
        return r
        """)
        assert self.unwrap(space, w_res) == [5, [2, 3, 7, 5], 8, 8, False]

    def test_module_eval_string_sees_the_callers_constants(self, space):
        w_res = space.execute("""
        module Outer
          module Nodes; X = 1; end
          class Builder
            class_eval "def x = Nodes::X"
          end
        end
        return Outer::Builder.new.x
        """)
        assert self.unwrap(space, w_res) == 1

    def test_enumerator_keeps_keywords(self, space):
        w_res = space.execute("""
        def lines(chomp: false) = chomp ? ["a"] : ["a\\n"]
        o = Object.new
        def o.each_line(chomp: false, &b) = (chomp ? ["x", "y"] : ["x\\n", "y\\n"]).each(&b)
        return [o.enum_for(:each_line, chomp: true).to_a, o.enum_for(:each_line).to_a]
        """)
        assert self.unwrap(space, w_res) == [["x", "y"], ["x\n", "y\n"]]


class TestExtensionsAndStringIO(BaseTopazTest):
    def test_missing_c_extension(self, space):
        with self.raises(space, "LoadError", "cannot load such file -- no_such_extension.so"):
            space.execute('require "no_such_extension.so"')

    def test_ffi_pointer_bytes_and_strings(self, space):
        w_res = space.execute("""
        require "ffi"
        mp = FFI::MemoryPointer.new(:char, 16)
        mp.put_bytes(0, "abcdef", 1, 3)
        mp.put_string(8, "hi")
        p2 = mp + 8
        return [mp.get_bytes(0, 3), mp.get_string(8), p2.class.name, p2.get_string(0),
                (mp.get_bytes(10, 20) rescue $!.class.name)]
        """)
        assert self.unwrap(space, w_res) == ["bcd", "hi", "FFI::Pointer", "hi", "IndexError"]

    def test_stringio(self, space):
        w_res = space.execute("""
        require "stringio"
        s = StringIO.new
        s << "ab" << 1
        s.puts "x", ["y", "z"]
        s.printf("%03d", 7)
        r = [s.string]
        s.rewind
        r << s.gets << s.read(2) << s.read << s.read(1) << s.eof?
        r << StringIO.new("line1\\nline2\\n").readlines << StringIO.new("x\\ny").each_line(chomp: true).to_a
        u = StringIO.new(+"hello")
        u.seek(2)
        u.write("XY")
        r << u.string
        a = StringIO.new(+"start", "a")
        a.write("-end")
        r << a.string << (StringIO.new("ro".freeze).write("x") rescue $!.class.name)
        return r
        """)
        assert self.unwrap(space, w_res) == [
            "ab1x\ny\nz\n007", "ab1x\n", "y\n", "z\n007", None, True,
            ["line1\n", "line2\n"], ["x", "y"], "heXYo", "start-end", "IOError"]


class TestPathnameAndFileNames(BaseTopazTest):
    def test_file_basename_and_extname(self, space):
        w_res = space.execute("""
        return [File.basename("/a/b/"), File.basename("/"), File.basename("a/b.rb", ".rb"),
                File.basename("b.rb", ".*"), File.basename(".rb", ".rb"), File.extname("x.rb"),
                File.extname(".bashrc"), File.extname("a.b/c"), File.extname("x."),
                File.extname("/x/y.tar.gz/")]
        """)
        assert self.unwrap(space, w_res) == [
            "b", "/", "b", "b", ".rb", ".rb", "", "", ".", ".gz"]

    def test_pathname(self, space):
        w_res = space.execute("""
        return [Pathname("/a/b/c").ascend.map(&:to_s), (Pathname("/usr/lib") + "../bin").to_s,
                Pathname("/a").join("b", "c").to_s, Pathname("/a/b/../c/./d").cleanpath.to_s,
                Pathname("/a/b/c").relative_path_from(Pathname("/a/x")).to_s,
                Pathname("x.rb").sub_ext(".txt").to_s, Pathname("/a/b").parent.to_s,
                (Pathname("/a") / "b").to_s, Pathname("/a").inspect,
                Pathname("/a/b/c").descend.map(&:to_s)]
        """)
        assert self.unwrap(space, w_res) == [
            ["/a/b/c", "/a/b", "/a", "/"], "/usr/bin", "/a/b/c", "/a/c/d", "../b/c", "x.txt",
            "/a", "/a/b", "#<Pathname:/a>", ["/", "/a", "/a/b", "/a/b/c"]]


class TestRescueAndSuper(BaseTopazTest):
    def test_rescue_inside_an_expression(self, space):
        w_res = space.execute("""
        r = []
        x = "a"
        r << (begin; x + (raise "q"); rescue; [2]; end)
        r << (begin; [x, x + (raise "q")]; rescue; 3; end)
        r << [1, 2].map { |i| begin; i + (i == 2 ? raise("w") : 0); rescue; -i; end }
        return r
        """)
        assert self.unwrap(space, w_res) == [[2], 3, [1, -2]]

    def test_retry_from_loops_and_nested_begins(self, space):
        w_res = space.execute("""
        r = []
        n = 0
        begin
          n += 1
          raise "a" if n < 3
        rescue
          begin
            retry
          rescue SystemCallError
          end
        end
        r << n
        n = 0
        begin
          n += 1
          raise "a" if n < 3
        rescue
          i = 0
          while i < 2
            i += 1
            retry if i == 1
          end
        end
        r << n
        return r
        """)
        assert self.unwrap(space, w_res) == [3, 3]

    def test_super_in_define_method(self, space):
        w_res = space.execute("""
        class A; def f(x, y = nil); "A#{x}#{y}"; end; def g; "Ag"; end; end
        class B < A
          define_method(:f) { |x| "B" + super(x, 2) }
          [:g].each { |m| define_method(m) { [1].map { super() }.first + "B" } }
        end
        return [B.new.f(1), B.new.g]
        """)
        assert self.unwrap(space, w_res) == ["BA12", "AgB"]


class TestDigestAndOpenSSL(BaseTopazTest):
    def run_with_libcrypto(self, space, source):
        w_res = space.execute("""
        begin
          require "topaz/libcrypto"
        rescue LoadError
          return :no_libcrypto
        end
        """ + source)
        if self.unwrap(space, w_res) == "no_libcrypto":
            pytest.skip("libcrypto is not available")
        return self.unwrap(space, w_res)

    def test_digest(self, space):
        res = self.run_with_libcrypto(space, """
        require "digest"
        d = Digest::SHA256.new
        d << "a"
        d.update("bc")
        return [Digest::MD5.hexdigest("abc"), Digest::SHA1.hexdigest(""), d.hexdigest[0, 8],
                d == Digest::SHA256.hexdigest("abc"), Digest::SHA2.new(384).digest_length,
                Digest(:SHA512).new.block_length, Digest::MD5.base64digest("abc")]
        """)
        assert res == ["900150983cd24fb0d6963f7d28e17f72",
                       "da39a3ee5e6b4b0d3255bfef95601890afd80709", "ba7816bf", True,
                       48, 128, "kAFQmDzST7DWlj99KOF/cg=="]

    def test_openssl(self, space):
        res = self.run_with_libcrypto(space, """
        require "openssl"
        r = [OpenSSL::Digest::SHA256.hexdigest("abc")[0, 8],
             OpenSSL::HMAC.hexdigest("SHA256", "key", "data")[0, 8],
             OpenSSL::PKCS5.pbkdf2_hmac("password", "salt", 1000, 32,
                                         OpenSSL::Digest::SHA256.new).unpack1("H*")[0, 8],
             OpenSSL::KDF.hkdf("secret", salt: "salt", info: "info", length: 42,
                               hash: "SHA256").unpack1("H*")[0, 8]]
        key = "k" * 32
        iv = "i" * 12
        c = OpenSSL::Cipher.new("aes-256-gcm")
        c.encrypt
        c.key = key
        c.iv = iv
        c.auth_data = "ad"
        ct = c.update("hello world") + c.final
        tag = c.auth_tag
        r << ct.unpack1("H*") << tag.unpack1("H*")
        d = OpenSSL::Cipher.new("aes-256-gcm")
        d.decrypt
        d.key = key
        d.iv = iv
        d.auth_tag = tag
        d.auth_data = "ad"
        r << d.update(ct) + d.final
        d = OpenSSL::Cipher::AES.new(128, :CBC)
        d.decrypt
        d.key = "q" * 16
        d.iv = "i" * 16
        r << (begin; d.update("x" * 16) + d.final; rescue OpenSSL::Cipher::CipherError => e; e.message; end)
        return r
        """)
        assert res == ["ba7816bf", "5031fe3d", "632c2812", "f6d2fcc4", "b2e194185dd8d66b893885",
                       "63b61fa99b1ab1b159bf671f01deba7f", "hello world",
                       "cipher final failed: bad decrypt"]


class TestStringScanner(BaseTopazTest):
    def test_scanning(self, space):
        w_res = space.execute("""
        require "strscan"
        s = StringScanner.new("3.14 is pi, hello world\\nline2")
        r = []
        r << s.scan(/\\d+/) << s.scan(/\\./) << s.scan(/\\d+/) << s.pos << s.scan(/x/) << s.matched?
        r << s.skip(/\\s+/) << s.check(/\\w+/) << s.pos << s.scan_until(/,/) << s.pre_match
        r << s.scan(/\\A\\s*(?<w>\\w+)/) << s[:w] << s.captures
        r << s.getch << s.peek(4) << s.bol? << s.scan_until(/\\n/) << s.bol?
        s.unscan
        r << s.pos << s.skip_until(/2/) << s.eos? << s.inspect
        t = StringScanner.new("abc")
        t.pos = 1
        r << t.scan(/^b/) << t.scan("c") << t.matched_size
        u = StringScanner.new("-42 0x1f")
        r << u.scan_integer << u.skip(/ /) << u.scan_integer(base: 16)
        return r
        """)
        assert self.unwrap(space, w_res) == [
            "3", ".", "14", 4, None, False, 1, "is", 5, "is pi,", "3.14 is pi",
            " hello", "hello", ["hello"], " ", "worl", False, "world\n", True,
            18, 11, True, "#<StringScanner fin>", "b", "c", 1, -42, 1, 31]


class TestJSONParser(BaseTopazTest):
    def test_parse(self, space):
        w_res = space.execute("""
        module JSON
          class JSONError < StandardError; end
          class ParserError < JSONError; attr_reader :line, :column; end
          class NestingError < ParserError; end
        end
        require "json/ext/parser"
        parse = ->(source, opts = nil) do
          JSON::Ext::ParserConfig.new(opts).parse(source)
        rescue JSON::ParserError => e
          [e.class.name, e.message]
        end
        return [
          parse.('{"a":[1,2.5,"x",null,true,false,{"b":-1e3}],"c":"\\u00e9\\n"}'),
          parse.('{"a":1}', symbolize_names: true),
          parse.('[1, 2,]', allow_trailing_comma: true),
          parse.('[[1]] // x', max_nesting: 1),
          parse.('[1 2]'), parse.('{"a" 1}'), parse.('01'), parse.('"abc'),
          parse.("[1,\\n  @]"), parse.('"\\ud83d\\ude00"').bytesize,
        ]
        """)
        assert self.unwrap(space, w_res) == [
            {"a": [1, 2.5, "x", None, True, False, {"b": -1000.0}], "c": "\xc3\xa9\n"},
            {"a": 1},
            [1, 2],
            ["JSON::NestingError", "nesting of 2 is too deep"],
            ["JSON::ParserError", "expected ',' or ']' after array value at line 1 column 4"],
            ["JSON::ParserError", "expected ':' after object key at line 1 column 6"],
            ["JSON::ParserError", "invalid number: '01' at line 1 column 1"],
            ["JSON::ParserError", 'unexpected end of input, expected closing " at line 1 column 5'],
            ["JSON::ParserError", "unexpected character: '@]' at line 1 column 3"],
            4,
        ]


class TestProcRuby2Keywords(BaseTopazTest):
    def test_proc_ruby2_keywords(self, space):
        w_res = space.execute("""
        def t(*a, **k) = [a, k]
        l = lambda { |*args, &b| t(*args, &b) }.ruby2_keywords
        m = lambda { |*args, &b| t(*args, &b) }
        return [l.call(1, x: 2), m.call(1, x: 2), l.lambda?]
        """)
        res = self.unwrap(space, w_res)
        assert res == [[[1], {"x": 2}], [[1, {"x": 2}], {}], True]


class TestLargeIntegerParsing(BaseTopazTest):
    def test_string_to_i_beyond_a_machine_word(self, space):
        w_res = space.execute("""
        return ["123456789012345678901".to_i.to_s, "-99999999999999999999".to_i.to_s,
                Integer("123456789012345678901").to_s, "ffffffffffffffffffff".to_i(16).to_s]
        """)
        assert self.unwrap(space, w_res) == [
            "123456789012345678901", "-99999999999999999999", "123456789012345678901",
            "1208925819614629174706175"]


class TestBigDecimal(BaseTopazTest):
    def test_bigdecimal(self, space):
        w_res = space.execute("""
        require "bigdecimal"
        b = ->(s) { BigDecimal(s) }
        return [
          (b.("1") / 3).to_s, (b.("2") / 3).to_s, (b.("1.23456789012345678901") / 3).to_s,
          b.("1.23").to_s, b.("-0.00123").to_s, b.("1.23").to_s("F"), b.("100").to_s("F"),
          b.("-0").to_s, b.("12345.678").to_s("3F"), b.("1.235").round(2).to_s,
          b.("1.245").round(2, :half_even).to_s, b.("-1.5").round, b.("123.456").floor(1).to_s,
          b.("1.23").precision, b.("0.001").scale, b.("0.00123").exponent,
          (b.("0.1") + b.("0.2")).to_s, (b.("1.5") * 0.1).to_s, b.("-7").divmod(3).map(&:to_s),
          b.("1") == 1, b.("1.5") <=> Rational(3, 2), (b.("1") / 0).to_s, b.("10").div(3),
          b.("10").div(3, 5).to_s, BigDecimal("1_000.5").to_s,
          (BigDecimal("1.5x") rescue $!.message), BigDecimal(Rational(1, 3), 5).to_s,
        ]
        """)
        assert self.unwrap(space, w_res) == [
            "0.33333333333333333333333333333333e0", "0.66666666666666666666666666666667e0",
            "0.4115226300411522630033333333333333333e0", "0.123e1", "-0.123e-2", "1.23",
            "100.0", "-0.0", "12 345.678", "0.124e1", "0.124e1", -2, "0.1234e3", 3, 3, -2,
            "0.3e0", "0.15e0", ["-0.3e1", "0.2e1"], True, 0, "Infinity", 3, "0.33333e1",
            "0.10005e4", 'invalid value for BigDecimal(): "1.5x"', "0.33333e0"]


class TestZlib(BaseTopazTest):
    def test_zlib(self, space):
        w_res = space.execute("""
        begin
          require "zlib"
        rescue LoadError
          return :no_libz
        end
        big = "hello world " * 5000
        d = Zlib::Deflate.deflate(big)
        io = StringIO.new("".b)
        gz = Zlib::GzipWriter.new(io)
        gz.write("line1\\n")
        gz.puts "line2"
        gz.close
        return [Zlib.crc32("abc"), Zlib.adler32("abc"), Zlib::Deflate.deflate("hello").unpack1("H*"),
                Zlib::Inflate.inflate(d) == big, Zlib.gunzip(Zlib.gzip("x" * 100)).size,
                Zlib::GzipReader.new(StringIO.new(io.string)).readlines,
                (begin; Zlib::Inflate.inflate("garbage"); rescue Zlib::DataError => e; e.message; end)]
        """)
        res = self.unwrap(space, w_res)
        if res == "no_libz":
            pytest.skip("libz is not available")
        assert res == [891568578, 38600999, "789ccb48cdc9c90700062c0215", True, 100,
                       ["line1\n", "line2\n"], "incorrect header check"]


class TestLineReading(BaseTopazTest):
    def test_readlines_gets_and_chomp(self, space, tmpdir):
        f = tmpdir.join("lines.txt")
        f.write("a\nbb\n\n\nccc\nd")
        w_res = space.execute("""
        path = %r
        r = []
        r << File.readlines(path) << File.readlines(path, chomp: true) << File.readlines(path, "b")
        r << File.readlines(path, 2) << File.readlines(path, "")
        File.open(path) { |f| r << f.gets << f.read(2) << f.gets << f.lineno << f.gets(nil) << f.gets << f.read << f.read(1) }
        IO.pipe { |rd, wr| wr.write("x\\ny\\n"); wr.close; r << rd.gets << rd.readlines }
        return r
        """ % (str(f),))
        assert self.unwrap(space, w_res) == [
            ["a\n", "bb\n", "\n", "\n", "ccc\n", "d"], ["a", "bb", "", "", "ccc", "d"],
            ["a\nb", "b", "\n\n\nccc\nd"], ["a\n", "bb", "\n", "\n", "\n", "cc", "c\n", "d"],
            ["a\nbb\n\n", "ccc\nd"], "a\n", "bb", "\n", 2, "\n\nccc\nd", None, "", None,
            "x\n", ["y\n"]]


class TestSystemExtensions(BaseTopazTest):
    def test_etc_socket_and_nonblock(self, space):
        w_res = space.execute("""
        require "etc"
        require "socket"
        require "io/nonblock"
        return [Etc.nprocessors > 0, Etc.getpwuid.is_a?(Etc::Passwd), Socket::AF_INET,
                Addrinfo.tcp("127.0.0.1", 80).inspect, $stdout.nonblock?,
                Process.uid == Process.euid, Socket.gethostname.is_a?(String)]
        """)
        assert self.unwrap(space, w_res) == [True, True, 2, "#<Addrinfo: 127.0.0.1:80>", False, True, True]


class TestRepeatedZeroWidthRegexps(BaseTopazTest):
    def test_repeated_groups_with_anchors(self, space):
        w_res = space.execute("""
        return [/(?:^a)+/.match("aa")&.[](0), /(?:\\bx)*y/.match("xy")&.[](0),
                /(a)(?:\\1)+/.match("aaa")&.[](0), /[^\\u00e9a]+/.match("bc\\u00e9")&.[](0)]
        """)
        assert self.unwrap(space, w_res) == ["a", "xy", "aaa", "bc"]


class TestPostCheckLoops(BaseTopazTest):
    def test_break_and_next_in_begin_end_while(self, space):
        w_res = space.execute("""
        r = []
        i = 0
        begin
          i += 1
          break if i == 3
          r << i
        end until false
        j = 0
        begin
          j += 1
          next if j == 2
          r << j
        end while j < 4
        return r
        """)
        assert self.unwrap(space, w_res) == [1, 2, 1, 3, 4]


class TestParameters(BaseTopazTest):
    def test_required_keywords_before_optional_ones(self, space):
        w_res = space.execute("""
        def a(k:, j: 2, m:) = [k, j, m]
        return [a(k: 1, m: 3), (a rescue $!.message), (a(k: 1) rescue $!.message)]
        """)
        assert self.unwrap(space, w_res) == [
            [1, 2, 3], "missing keywords: :k, :m", "missing keyword: :m"]

    def test_parameters(self, space):
        w_res = space.execute("""
        class C
          def a(x, y = 1, *r, k:, **kw, &b); end
          def c(*, **, &); end
          attr_reader :e
          define_method(:f) { |q, w = 1| }
        end
        return [C.instance_method(:a).parameters, C.instance_method(:c).parameters,
                C.instance_method(:e).parameters, C.instance_method(:f).parameters,
                proc { |x, y| }.parameters, lambda { |x, y| }.parameters,
                proc { |x| }.parameters(lambda: true), [].method(:push).parameters]
        """)
        assert self.unwrap(space, w_res) == [
            [["req", "x"], ["opt", "y"], ["rest", "r"], ["keyreq", "k"], ["keyrest", "kw"], ["block", "b"]],
            [["rest", "*"], ["keyrest", "**"], ["block", "&"]], [], [["req", "q"], ["opt", "w"]],
            [["opt", "x"], ["opt", "y"]], [["req", "x"], ["req", "y"]], [["req", "x"]], [["rest"]]]


class TestInheritedHook(BaseTopazTest):
    def test_inherited_can_call_class_methods_on_the_subclass(self, space):
        w_res = space.execute("""
        r = []
        class A; def self.inherited(s) = (@@r << [s.name, s.bump]); def self.bump = 1; end
        A.class_variable_set(:@@r, r)
        class B < A; end
        Class.new(A)
        return r
        """)
        assert self.unwrap(space, w_res) == [["B", 1], [None, 1]]


class TestSQLite3Native(BaseTopazTest):
    def test_native_layer(self, space):
        w_res = space.execute("""
        begin
          require "sqlite3/sqlite3_native"
        rescue LoadError
          return :no_libsqlite3
        end
        module SQLite3
          class Exception < ::StandardError; attr_reader :code; end
          class SQLException < Exception; end
          class ConstraintException < Exception; end
        end
        db = SQLite3::Database.allocate
        db.__send__(:open_v2, ":memory:", 6, nil)
        run = ->(sql, *binds) do
          st = SQLite3::Statement.allocate
          st.__send__(:prepare, db, sql)
          binds.each_with_index { |v, i| st.bind_param(i + 1, v) }
          rows = []
          while (row = st.step)
            rows << row
          end
          st.close
          rows
        end
        run.("create table t (id integer primary key, name text, score real)")
        run.("insert into t (name, score) values (?, ?)", "alice", 1.5)
        run.("insert into t (name, score) values (?, ?)", "bob", nil)
        r = [run.("select id, name, score from t order by id"), db.last_insert_row_id, db.changes]
        r << (begin; run.("select nope from t"); rescue SQLite3::SQLException => e; e.message; end)
        r << (begin; run.("insert into t (id) values (1)"); rescue SQLite3::ConstraintException => e; e.message; end)
        r << db.exec_batch("create table u(x); insert into u values (1); select x from u; -- done", false)
        db.close
        return r
        """)
        res = self.unwrap(space, w_res)
        if res == "no_libsqlite3":
            pytest.skip("libsqlite3 is not available")
        assert res == [[[1, "alice", 1.5], [2, "bob", None]], 2, 1, "no such column: nope",
                       "UNIQUE constraint failed: t.id", [[1]]]


class TestEvalWithLocation(BaseTopazTest):
    def test_eval_with_binding_file_and_line(self, space):
        w_res = space.execute("""
        x = 5
        r = [eval("x * 2", nil, "f.rb", 10), eval("[__FILE__, __LINE__]", nil, "g.rb", 42),
             binding.eval("x + 3", "h.rb", 7)]
        r << (begin; eval("raise 'boom'", nil, "e.rb", 99); rescue => e; e.backtrace[0]; end)
        return r
        """)
        assert self.unwrap(space, w_res) == [10, ["g.rb", 42], 8, "e.rb:99:in '<main>'"]


class TestBCryptExt(BaseTopazTest):
    def test_bcrypt_engine(self, space):
        w_res = space.execute("""
        begin
          require "bcrypt_ext"
        rescue LoadError
          return :no_libcrypt
        end
        salt = BCrypt::Engine.__bc_salt("$2a$", 5, "0123456789abcdef")
        return [BCrypt::Engine.__bc_crypt("secret", "$2a$04$abcdefghijklmnopqrstuu"),
                salt[0, 7], salt.size, BCrypt::Engine.__bc_crypt(nil, salt)]
        """)
        res = self.unwrap(space, w_res)
        if res == "no_libcrypt":
            pytest.skip("libcrypt is not available")
        assert res == ["$2a$04$abcdefghijklmnopqrstuu2r9OfJnfCsdneAXAGHnS4UpFFP8WIrW", "$2a$05$", 29, None]


class TestAutoloadShadowing(BaseTopazTest):
    def test_autoload_shadows_an_inherited_constant(self, space, tmpdir):
        f = tmpdir.join("b_conf.rb")
        f.write("class B; class Conf; def who = :b; end; end\n")
        w_res = space.execute("""
        class A; class Conf; def who = :a; end; end
        class B < A
          autoload :Conf, %r
          def self.make = B::Conf.new.who
        end
        return [B.autoload?(:Conf).nil?, B.make, A::Conf.new.who]
        """ % (str(f),))
        assert self.unwrap(space, w_res) == [False, "b", "a"]


class TestMatchSetsCallersLastMatch(BaseTopazTest):
    def test_symbol_and_string_match(self, space):
        w_res = space.execute("""
        r = []
        r << (:visit_X =~ /^visit_(.*)$/) << $1
        m = :abc.match(/b(c)/)
        r << m[1] << $~[0] << :abc.match?(/z/) << :hello[/l+/] << $~[0]
        [:visit_A, :visit_B].each { |pim| next unless pim =~ /^visit_(.*)$/; r << $1 }
        "abc".match(/b(c)/)
        r << $~[0]
        "xy".match("y") { |md| r << md[0] }
        return r
        """)
        assert self.unwrap(space, w_res) == [0, "X", "c", "bc", False, "ll", "ll", "A", "B", "bc", "y"]


class TestUndefAndRemoveSeveralMethods(BaseTopazTest):
    def test_several_names(self, space):
        w_res = space.execute("""
        class A; def a;end; def b;end; def c;end; def d;end; undef_method :a, :b; remove_method :c, :d; end
        return [A.method_defined?(:a), A.method_defined?(:b), A.method_defined?(:c), A.method_defined?(:d)]
        """)
        assert self.unwrap(space, w_res) == [False, False, False, False]


class TestJoinNewAndGrep(BaseTopazTest):
    def test_join_flattens_nested_arrays(self, space):
        w_res = space.execute("""
        a = [1]
        a << a
        return [[["a", "b"], "c"].join(" | "), [1, [2, [3]]].join(","), [:x, nil, 2.5].join("-"),
                [1, 2].join(nil), (a.join rescue $!.message)]
        """)
        assert self.unwrap(space, w_res) == ["a | b | c", "1,2,3", "x--2.5", "12", "recursive array join"]

    def test_string_new_with_encoding_and_capacity(self, space):
        w_res = space.execute("""
        return [String.new.encoding.to_s, String.new("x").encoding.to_s,
                String.new(encoding: "UTF-8").encoding.to_s, String.new("ab", capacity: 10)]
        """)
        assert self.unwrap(space, w_res) == ["ASCII-8BIT", "UTF-8", "UTF-8", "ab"]

    def test_grep_block_sees_the_match(self, space):
        w_res = space.execute("""
        return [%w[on_a xb on_c].grep(/\\Aon_/) { $'.to_sym }, %w[a1 b2].grep(/(\\d)/) { $1 }]
        """)
        assert self.unwrap(space, w_res) == [["a", "c"], ["1", "2"]]


class TestStructKeywordInit(BaseTopazTest):
    def test_keyword_init(self, space):
        w_res = space.execute("""
        a = Struct.new(:a, :b, keyword_init: true)
        b = Struct.new(:a, :b)
        c = Struct.new(:a, keyword_init: false)
        return [a.new(a: 1, b: 2).to_a, (a.new(1) rescue $!.message), (a.new(c: 1) rescue $!.message),
                a.keyword_init?, b.new(1, 2).to_a, b.new(a: 5).to_a, b.new({a: 5}).to_a[1], b.keyword_init?,
                c.new(a: 1).to_a.size, (b.new(1, 2, 3) rescue $!.message)]
        """)
        assert self.unwrap(space, w_res) == [
            [1, 2], "wrong number of arguments (given 1, expected 0)", "unknown keywords: c", True,
            [1, 2], [5, None], None, None, 1, "struct size differs"]


class TestMarklyAndNokogiriNative(BaseTopazTest):
    def test_markly_native(self, space):
        w_res = space.execute("""
        begin
          require "markly/markly"
        rescue LoadError
          return :no_libcmark
        end
        parser = Markly::Parser.new(0)
        parser.enable(:strikethrough)
        root = parser.parse("# Hi\\n\\nSome *em* and ~~gone~~")
        heading = root.first_child
        types = [root.type, heading.type, heading.next.type, heading.header_level,
                 heading.first_child.string_content]
        link = Markly::Node.new(:link)
        link.url = "/u/bob"
        text = Markly::Node.new(:text)
        text.string_content = "@bob"
        link.append_child(text)
        heading.first_child.insert_after(link)
        return types + [root.__send__(:_render_html, 0, [:strikethrough])]
        """)
        res = self.unwrap(space, w_res)
        if res == "no_libcmark":
            pytest.skip("libcmark-gfm is not available")
        assert res == ["document", "header", "paragraph", 1, "Hi",
                       '<h1>Hi<a href="/u/bob">@bob</a></h1>\n<p>Some <em>em</em> and <del>gone</del></p>\n']


class TestRedo(BaseTopazTest):
    def test_redo_in_blocks_and_loops(self, space):
        w_res = space.execute("""
        r = []
        tries = 0
        [1, 2].each do |x|
          tries += 1
          r << [x, tries]
          redo if x == 1 && tries < 3
        end
        i = 0
        n = 0
        while i < 3
          i += 1
          n += 1
          redo if n == 2
          r << i
        end
        r << n
        return r
        """)
        assert self.unwrap(space, w_res) == [[1, 1], [1, 2], [1, 3], [2, 4], 1, 3, 3]


class TestModuleNewBlockConstants(BaseTopazTest):
    def test_constants_from_where_the_block_is_written(self, space):
        w_res = space.execute("""
        class Outer
          K = 7
          H = Module.new do
            module_function
            def get = K
          end
          C = Class.new { def k = K }
        end
        return [Outer::H.get, Outer::C.new.k]
        """)
        assert self.unwrap(space, w_res) == [7, 7]


class TestGlobalAlias(BaseTopazTest):
    def test_alias_global_variables(self, space):
        w_res = space.execute("""
        $foo = 1
        alias $bar $foo
        r = [$bar]
        $bar = 2
        r << $foo
        alias $ERROR_INFO $!
        begin; raise "x"; rescue; r << $ERROR_INFO.message; end
        alias $new_one $never_set
        r << $new_one
        return r
        """)
        assert self.unwrap(space, w_res) == [1, 2, "x", None]


class TestClassVariablesInSingletonClassBodies(BaseTopazTest):
    def test_class_variables_of_the_enclosing_module(self, space):
        w_res = space.execute("""
        module F
          @@a = {}
          class << self
            def singleton_method_added(n) = (@@a[n] = true)
            def got = @@a
            def put(x) = (@@b = x)
          end
          def self.later = 1
          def self.b = @@b
        end
        F.put(5)
        return [F.got.keys, F.b, F.class_variable_get(:@@b)]
        """)
        assert self.unwrap(space, w_res) == [
            ["singleton_method_added", "got", "put", "later", "b"], 5, 5]


class TestApproximateRefinements(BaseTopazTest):
    def test_refinements_add_methods(self, space):
        w_res = space.execute("""
        module DC
          refine Object do
            def dclone = clone
          end
          refine String do
            def upcase = "never"
            def shout = upcase + "!"
          end
        end
        using DC
        class User
          using DC
          def run = ["a".dclone, "hi".shout, "x".upcase]
        end
        return User.new.run + [DC.refinements.size]
        """)
        assert self.unwrap(space, w_res) == ["a", "HI!", "X", 2]


class TestTopLevelAutoload(BaseTopazTest):
    def test_top_level_autoload_is_on_object(self, space, tmpdir):
        f = tmpdir.join("mimey.rb")
        f.write("module Mimey; X = 1; end\n")
        w_res = space.execute("""
        autoload :Mimey, %r
        r = [Object.autoload?(:Mimey).nil?]
        module A; module B; def self.f = Mimey::X; end; end
        return r + [A::B.f]
        """ % (str(f),))
        assert self.unwrap(space, w_res) == [False, 1]


class TestSingletonClassesAreNotSubclasses(BaseTopazTest):
    def test_inherited_is_not_called_for_singleton_classes(self, space):
        w_res = space.execute("""
        r = []
        class P; def self.inherited(k) = (@@r << k.name); end
        P.class_variable_set(:@@r, r)
        class Q < P; end
        x = Q.new
        class << x; def hi = 1; end
        y = P.new
        def y.z = 2
        return [r, P.subclasses.map(&:name), x.hi]
        """)
        assert self.unwrap(space, w_res) == [["Q"], ["Q"], 1]


class TestDirGlobBase(BaseTopazTest):
    def test_glob_with_base_and_several_patterns(self, space, tmpdir):
        tmpdir.join("a", "b").ensure(dir=True)
        tmpdir.join("a", "x.rb").write("")
        tmpdir.join("a", "b", "y.rb").write("")
        tmpdir.join("z.txt").write("")
        w_res = space.execute("""
        base = %r
        return [Dir.glob("**/*.rb", base: base), Dir.glob("*", base: base + "/"),
                Dir.glob([base + "/*.txt", base + "/a/*.rb"]).map { |f| File.basename(f) }]
        """ % (str(tmpdir),))
        assert self.unwrap(space, w_res) == [["a/b/y.rb", "a/x.rb"], ["a", "z.txt"], ["z.txt", "x.rb"]]


class TestGsubBangLastMatch(BaseTopazTest):
    def test_gsub_bang_block_sees_the_match(self, space):
        w_res = space.execute("""
        s = +"foo_bar/baz"
        r = [s.gsub!(/(?:_|(\\/))([a-z\\d]*)/i) { w = $2; $1 ? "::#{w.capitalize}" : w.capitalize }]
        t = +"abc"
        r << t.sub!(/(b)/) { $1.upcase }.dup << t.gsub!(/z/, "") << t.sub!("a", "A")
        "x".gsub!(/(x)/, "y")
        r << $1
        return r
        """)
        assert self.unwrap(space, w_res) == ["fooBar::Baz", "aBc", None, "ABc", "x"]


class TestBeginElseValue(BaseTopazTest):
    def test_the_else_clause_gives_the_value(self, space):
        w_res = space.execute("""
        def a = (begin; 1; rescue; 2; else; 3; end)
        def b
          :body
        rescue LoadError
          :rescued
        else
          :else
        end
        def c = (begin; 1; rescue; 2; end)
        def d = (begin; raise "x"; rescue; 2; else; 3; end)
        return [a, b, c, d]
        """)
        assert self.unwrap(space, w_res) == [3, "else", 1, 2]


class TestDefinitionReturnValues(BaseTopazTest):
    def test_alias_method_and_define_method_return_names(self, space):
        w_res = space.execute("""
        class A
          R = [alias_method(:a2, :to_s), define_method(:d) {}, define_method(:e, instance_method(:d))]
          public alias_method(:reset, :initialize)
        end
        return A::R + [A.public_method_defined?(:reset)]
        """)
        assert self.unwrap(space, w_res) == ["a2", "d", "e", True]


class TestSubexpCallsAndGroupNumbers(BaseTopazTest):
    def test_subexpression_calls_and_backreferences(self, space):
        w_res = space.execute("""
        t = lambda { |src, s| m = Regexp.new(src).match(s); m ? m[0] : nil }
        return [t.("(?<a>[bc])\\\\g<a>", "bc"), t.("(?<s>x){0}\\\\g<s>+", "xxx"), t.("(?<a>b)\\\\k<a>", "bb"),
                t.("(?<a>b)\\\\k<a>", "bc"), t.("(a|b)\\\\g<1>", "ab")]
        """)
        assert self.unwrap(space, w_res) == ["bc", "xxx", "bb", None, "ab"]

    def test_group_numbers_with_names_and_hidden_groups(self, space):
        w_res = space.execute("""
        return [/(?<a>x)(?<b-c>y)/.names, /(?<a>x)(y)(?<b>z)/.named_captures,
                /(?<a>x)(y)(?<b>z)/.match("xyz").captures, /(a)(?>b)(c)/.match("abc").captures,
                /a*+(b)/.match("aab")[1], /(?<n>a)*+(?<m>b)/.match("aab")[:m]]
        """)
        assert self.unwrap(space, w_res) == [["a", "b-c"], {"a": [1], "b": [2]}, ["x", "z"], ["a", "c"], "b", "b"]


class TestFileReadOptions(BaseTopazTest):
    def test_file_read_with_length_offset_and_encodings(self, space, tmpdir):
        f = tmpdir.join("rd.txt")
        f.write("hello world")
        w_res = space.execute("""
        path = %r
        return [File.read(path), File.read(path, 5), File.read(path, 3, 6),
                File.read(path, external_encoding: Encoding::UTF_8, internal_encoding: Encoding::UTF_8).encoding.to_s,
                File.read(path, mode: "rb").encoding.to_s, File.read(path, 5).encoding.to_s]
        """ % (str(f),))
        assert self.unwrap(space, w_res) == ["hello world", "hello", "wor", "UTF-8", "ASCII-8BIT", "ASCII-8BIT"]


class TestEnumerablePatterns(BaseTopazTest):
    def test_all_any_one_none_with_a_pattern(self, space):
        w_res = space.execute("""
        return [[1, 2].all?(Integer), [1, "a"].all?(Integer), %w[ab cd].any?(/c/), [nil, 1].one?(nil),
                [1, 2].none?(3..5), {a: 1}.any?(Array), [nil, false].all?(nil)]
        """)
        assert self.unwrap(space, w_res) == [True, False, True, True, True, True, False]


class TestMethodListsByVisibility(BaseTopazTest):
    def test_method_lists_use_the_effective_visibility(self, space):
        w_res = space.execute("""
        class A; def pub; end; private def priv; end; protected def prot; end; end
        class B < A; private :pub; end
        return [Module.instance_methods.grep(/initialize|method_missing/), A.instance_methods(false).sort,
                A.private_instance_methods(false), B.instance_methods.include?(:pub),
                B.private_instance_methods.include?(:pub), A.new.methods.include?(:priv),
                A.new.private_methods.include?(:priv), A.protected_instance_methods(false)]
        """)
        assert self.unwrap(space, w_res) == [[], ["prot", "pub"], ["priv"], False, True, False, True, ["prot"]]


class TestRecursiveSubexpCalls(BaseTopazTest):
    def test_recursive_calls(self, space):
        w_res = space.execute("""
        m1 = /\\A((?:((?:\\w+\\.)?\\w+ | \\w+\\((?:|\\g<2>)\\)))(?:(?:\\s+AS)?\\s+\\w+)?)(?:\\s*,\\s*\\g<1>)*\\z/ix
        return [m1.match?("posts.id"), m1.match?("count(posts.id) AS c, name"), m1.match?("lower(trim(x))"),
                m1.match?("id; drop"), /(?<p>\\((?:\\g<p>)*\\))/.match("(())")[0],
                (Regexp.new("\\\\g<x>") rescue $!.class)]
        """)
        assert self.unwrap(space, w_res)[:5] == [True, True, True, False, "(())"]
        assert space.str_w(space.send(space.listview(w_res)[5], "name")) == "RegexpError"


class TestBindingDupAndNewLocals(BaseTopazTest):
    def test_dup_and_new_local_variables(self, space):
        w_res = space.execute("""
        x = 1
        b = binding.dup
        b.local_variable_set(:y, 5)
        b2 = TOPLEVEL_BINDING.dup
        b2.local_variable_set(:name, "w")
        return [b.eval("x + y"), b.local_variable_get(:y), b.local_variable_defined?(:y),
                b2.eval("name * 2"), defined?(y)]
        """)
        assert self.unwrap(space, w_res) == [6, 5, True, "ww", None]


class TestConstPaths(BaseTopazTest):
    def test_const_get_and_const_defined_with_paths(self, space):
        w_res = space.execute("""
        module Outer; module Inner; X = 1; end; end
        return [Object.const_get("Outer::Inner::X"), Object.const_defined?("Outer::Inner"),
                Object.const_get("::Outer").name, Object.const_defined?("Outer::Nope"),
                Object.const_defined?("Nope::X"), (Object.const_get("Outer::") rescue $!.class.name)]
        """)
        assert self.unwrap(space, w_res) == [1, True, "Outer", False, False, "NameError"]


class TestMarshalInRuby(BaseTopazTest):
    def test_round_trips_and_cruby_bytes(self, space):
        w_res = space.execute("""
        s = Struct.new(:a, :b)
        Object.const_set(:MarshalS, s)
        objs = [nil, true, 0, -124, 2**30, -(2**70), 1.5, 100.0, 1e-5, "héllo", "bin\\xff".b, :sym,
                [1, [2, 3]], {a: 1, "b" => [2]}, MarshalS.new(1, "x"), 1...3, Hash.new(5).merge(a: 1), /ab+c/i, String]
        ok = objs.all? { |o| back = Marshal.load(Marshal.dump(o)); back == o && (!o.is_a?(Hash) || back.default == o.default) }
        shared = "s"
        b = Marshal.load(Marshal.dump([shared, shared]))
        return [ok, b[0].equal?(b[1]), Marshal.dump([1, "a", :b, 1e2]).bytes, Marshal.load(Marshal.dump("\\u00e9")).encoding.to_s]
        """)
        assert self.unwrap(space, w_res) == [
            True, True, [4, 8, 91, 9, 105, 6, 73, 34, 6, 97, 6, 58, 6, 69, 84, 58, 6, 98, 102, 8, 49, 101, 50], "UTF-8"]


class TestSearchAnchor(BaseTopazTest):
    def test_leading_g_anchors_each_search(self, space):
        w_res = space.execute("""
        token = /\\G(?:[\\s]+|\\(|\\)|[a-z]+|.)/
        return ["(send $_ ...)".scan(token), "aab".scan(/\\Ga/), "xaa".scan(/\\Ga/), "ab12".gsub(/\\G[a-z]/, "_")]
        """)
        assert self.unwrap(space, w_res) == [
            ["(", "send", " ", "$", "_", " ", ".", ".", ".", ")"], ["a", "a"], [], "__12"]


class TestStackedQuantifiers(BaseTopazTest):
    def test_quantifiers_stack(self, space):
        w_res = space.execute("""
        return ["aaaa"[/a{2}*/], "aaa"[/a{2}+/], "ab"[/a**b/], "xaaaaax"[/a{2}{2}/]]
        """)
        assert self.unwrap(space, w_res) == ["aaaa", "aa", "ab", "aaaa"]


class TestDirChildren(BaseTopazTest):
    def test_children_each_child_and_each(self, space, tmpdir):
        tmpdir.join("a").write("")
        tmpdir.join("b").write("")
        tmpdir.join("s").ensure(dir=True)
        w_res = space.execute("""
        d = %r
        return [Dir.children(d).sort, Dir.each_child(d).to_a.sort, Dir.empty?(d + "/s"), Dir.empty?(d),
                Dir.new(d).children.sort, Dir.new(d).to_a.size, Dir.home.is_a?(String)]
        """ % (str(tmpdir),))
        assert self.unwrap(space, w_res) == [["a", "b", "s"], ["a", "b", "s"], True, False, ["a", "b", "s"], 5, True]


class TestStructToH(BaseTopazTest):
    def test_struct_to_h(self, space):
        w_res = space.execute("""
        s = Struct.new(:a, :b).new(1, 2)
        return [s.to_h, s.to_h { |k, v| [k.to_s, v * 2] }]
        """)
        assert self.unwrap(space, w_res) == [{"a": 1, "b": 2}, {"a": 2, "b": 4}]


class TestIncludeFlattensModules(BaseTopazTest):
    def test_super_reaches_modules_included_by_included_modules(self, space):
        w_res = space.execute("""
        module R; def mfh(a) = [:r, a]; end
        module CM1; include R; end
        module CM2; def mfh(a) = super(a + [1]); end
        class C; extend CM1; extend CM2; end
        class E; include CM1; end
        return [C.mfh([0]), E.ancestors.take(3).map(&:name)]
        """)
        assert self.unwrap(space, w_res) == [["r", [0, 1]], ["E", "CM1", "R"]]


class TestNameErrorReceiver(BaseTopazTest):
    def test_name_and_receiver(self, space):
        w_res = space.execute("""
        r = []
        begin; Nope; rescue NameError => e; r << [e.name, e.receiver == Object]; end
        module Mm; end
        begin; Mm::Zz; rescue NameError => e; r << [e.name, e.receiver == Mm]; end
        begin; 5.nope_x; rescue NameError => e; r << [e.name, e.receiver]; end
        e = NameError.new("m", :x, receiver: 3)
        r << [e.name, e.receiver]
        r << (begin; NameError.new("m").receiver; rescue ArgumentError => x; x.message; end)
        return r
        """)
        assert self.unwrap(space, w_res) == [
            ["Nope", True], ["Zz", True], ["nope_x", 5], ["x", 3], "no receiver is available"]


class TestWhenSplat(BaseTopazTest):
    def test_when_with_splat(self, space):
        w_res = space.execute("""
        a = [:a, :b]
        b = [:c]
        r = [:a, :c, :z].map { |n| case n; when *a then 1; when *b, :z then 2; else 3; end }
        w = case; when *[false, nil] then 1; when *[nil, 2] then 2; end
        return [r, w, (case 5; when *[] then 1; else 0; end)]
        """)
        assert self.unwrap(space, w_res) == [[1, 2, 2], 2, 0]


class TestRangeStepRational(BaseTopazTest):
    def test_rational_steps(self, space):
        w_res = space.execute("""
        return [((0r..1r) % 0.25r).map(&:to_s), (1..2).step(1/2r).map(&:to_s), (1..10).step(3).to_a]
        """)
        assert self.unwrap(space, w_res) == [["0/1", "1/4", "1/2", "3/4", "1/1"], ["1", "3/2", "2/1"], [1, 4, 7, 10]]


class TestDefinedScopedConstant(BaseTopazTest):
    def test_defined_scoped_constant_skips_object(self, space):
        w_res = space.execute("""
        module M; end
        class K; end
        module N; R = defined?(String); end
        return [defined?(M::Struct), defined?(K::Struct), defined?(Object::String), N::R]
        """)
        assert self.unwrap(space, w_res) == [None, None, "constant", "constant"]


class TestBigLiteralArrays(BaseTopazTest):
    def test_big_constant_arrays(self, space):
        items = ", ".join(str(i % 300) for i in range(70000))
        w_res = space.execute("""
        def f = [%s]
        a = f
        a << :x
        b = [1, nil, :s, 1.5, true] + (1..70).to_a
        return [a.size, f.size, a[1], f.last, b.size]
        """ % items)
        assert self.unwrap(space, w_res) == [70001, 70000, 1, 69999 % 300, 75]


class TestLastMatchNilAndErrinfo(BaseTopazTest):
    def test_numbered_globals_after_a_failed_match(self, space):
        w_res = space.execute("""
        "x" =~ /(y)/
        r = [$1, $&, $+, $`, $']
        "q".sub(/(z)/, "")
        r << $1
        return r
        """)
        assert self.unwrap(space, w_res) == [None] * 6

    def test_next_and_break_out_of_a_rescue_clause_restore_errinfo(self, space):
        w_res = space.execute("""
        r = []
        [1, 2].each do |x|
          begin
            raise "boom" if x == 1
          rescue
            next
          end
        end
        r << $!
        [1].each { begin; raise "b2"; rescue; break; end }
        r << $!
        return r
        """)
        assert self.unwrap(space, w_res) == [None, None]


class TestRegexpLastMatch(BaseTopazTest):
    def test_last_match_in_a_scan_block(self, space):
        w_res = space.execute("""
        r = []
        "a1b2".scan(/([a-z])(\\d)/) { r << [Regexp.last_match.begin(0), Regexp.last_match(2)] }
        "x" =~ /(x)/
        r << Regexp.last_match(1)
        "y" =~ /z/
        r << Regexp.last_match
        return r
        """)
        assert self.unwrap(space, w_res) == [[0, "1"], [2, "2"], "x", None]


class TestMethodOwner(BaseTopazTest):
    def test_owner_is_the_defining_module(self, space):
        w_res = space.execute("""
        module CM; def ds; end; end
        class B; extend CM; end
        class U < B; end
        return [U.method(:ds).owner.name, B.is_a?(U.method(:ds).owner),
                U.new.method(:to_s).owner.name, U.instance_method(:inspect).owner.name]
        """)
        assert self.unwrap(space, w_res) == ["CM", True, "Kernel", "Kernel"]


class TestBindModuleMethods(BaseTopazTest):
    def test_module_methods_bind_to_any_object(self, space):
        w_res = space.execute("""
        m = Module.new { def f; 1; end }
        class C; end
        C.define_method(:g, m.instance_method(:f))
        r = [m.instance_method(:f).bind(Object.new).call, C.new.g]
        begin; String.instance_method(:upcase).bind(1); rescue TypeError => e; r << e.message; end
        return r
        """)
        assert self.unwrap(space, w_res) == [1, 1, "bind argument must be an instance of String"]


class TestBlockArgsDoNotMutate(BaseTopazTest):
    def test_destructuring_leaves_the_array_alone(self, space):
        w_res = space.execute("""
        a = [1, 2, 3]
        proc { |x, y| }.call(a)
        b = [4, 5, 6]
        [b].each { |x, y| }
        c = [7]
        [c].each { |x, y, z| }
        return [a, b, c, [[1, 2, 3]].select { |x, y| true }]
        """)
        assert self.unwrap(space, w_res) == [[1, 2, 3], [4, 5, 6], [7], [[1, 2, 3]]]


class TestErrnoClasses(BaseTopazTest):
    def test_errno_classes(self, space):
        w_res = space.execute("""
        r = [Errno::ENOENT.new.message, Errno::ENOENT.new("x").message,
             Errno::ENOENT.new.errno, Errno::EMFILE::Errno > 0,
             Errno::EAGAIN.equal?(Errno::EWOULDBLOCK), Errno::ENOENT.name,
             Errno::ENOENT.superclass == SystemCallError]
        begin
          File.read("/nonexistent-file")
        rescue SystemCallError => e
          r << e.class.name << e.errno << e.message
        end
        return r
        """)
        assert self.unwrap(space, w_res) == [
            "No such file or directory", "No such file or directory - x", 2, True,
            True, "Errno::ENOENT", True, "Errno::ENOENT", 2, "No such file or directory"]


class TestStrictInteger(BaseTopazTest):
    def test_kernel_integer_parses_strictly(self, space):
        w_res = space.execute("""
        r = []
        ["12", " 12 ", "-0x1F", "0b101", "0o17", "017", "1_000", "08", "x", "1__0", "", "0x", "12a"].each do |s|
          r << (begin; Integer(s); rescue ArgumentError; :err; end)
        end
        r << Integer("ff", 16) << Integer("0b1", 16) << Integer("z", exception: false)
        return r
        """)
        assert self.unwrap(space, w_res) == [
            12, 12, -31, 5, 15, 15, 1000, "err", "err", "err", "err", "err", "err",
            255, 177, None]


class TestRescueModifierAndRetry(BaseTopazTest):
    def test_rescue_modifier_in_a_module_function(self, space):
        w_res = space.execute("""
        module RM
          module Inner
            def self.const_missing(name) = raise(NameError, "missing #{name}")
            def self.g(v) = (Integer(v) rescue v)
          end
        end
        return RM::Inner.g("q")
        """)
        assert self.unwrap(space, w_res) == "q"

    def test_retry_restores_errinfo(self, space):
        w_res = space.execute("""
        n = 0
        r = nil
        begin
          n += 1
          raise "a" if n < 3
          r = $!
        rescue
          retry
        end
        return [r, n]
        """)
        assert self.unwrap(space, w_res) == [None, 3]
