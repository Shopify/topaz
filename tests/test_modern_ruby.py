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
