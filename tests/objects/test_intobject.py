import math
import operator
import sys

from rpython.rlib.rarithmetic import LONG_BIT
from rpython.rlib.rbigint import rbigint

from ..base import BaseTopazTest


class TestFixnumObject(BaseTopazTest):
    def test_gcd(self, space):
        w_res = space.execute("""
        return [12.gcd(18), -12.gcd(18), 12.gcd(-18), 0.gcd(5), 5.gcd(0), 0.gcd(0),
                7.gcd(2**70), (2**70).gcd(6), (-2**63).gcd(2), 6.gcd(-2**63)]
        """)
        assert self.unwrap(space, w_res) == [6, 6, 6, 5, 5, 0, 1, 2, 2, 2]
        with self.raises(space, "TypeError"):
            space.execute("3.gcd(1.5)")

    def test_eqlp(self, space):
        w_res = space.execute("""
        class S < String; end
        class K; def eql?(o); o == "k"; end; def hash; "k".hash; end; end
        h = {1 => :a, "k" => :b, :s => :c, 2**70 => :d, 1.0 => :e}
        return [
          1.eql?(1), 1.eql?(1.0), 1.eql?(2), 1.eql?(2**70), 1.eql?(nil),
          h[1], h[1.0], h["k"], h["k".dup], h[:s], h[2**70], h[S.new("k")],
          h.key?(S.new("zz")), h[K.new], {S.new("k") => 1}["k"], {K.new => 1}["k"],
        ]
        """)
        assert self.unwrap(space, w_res) == [
            True, False, False, False, False,
            "a", "e", "b", "b", "c", "d", "b",
            False, "b", 1, None,
        ]

    def test_step(self, space):
        w_res = space.execute("""
        r = []
        res = []
        res << (1.step(10, 3) { |i| r << i }); res << r
        r = []; 10.step(1, -3) { |i| r << i }; res << r
        r = []; 1.step(3) { |i| r << i }; res << r
        r = []; 1.step(2, 0.5) { |i| r << i }; res << r
        r = []; 1.step(by: 2, to: 7) { |i| r << i }; res << r
        r = []; 1.step(7, by: 2) { |i| r << i }; res << r
        r = []; 1.step(3) { |i| r << i; break :brk if i == 2 }; res << r
        res << 1.step(10, 3).to_a << 1.step(10, 3).size << 3.step(1).to_a << 1.step(1).to_a
        res << 1.step(nil, 2).first(3) << 1.step(by: -1).first(3) << 1.step(3, 1.0).to_a
        res << 1.step(2, 0.3).to_a << 1.step(10, 2.5).size << 1.step(0, 2).size << 1.step(10, -1).size
        res << 1.step(1.0, 0.3).to_a << 1.step(-1.0, -0.5).to_a << 1.step(10, nil).to_a.size
        res << 1.step(3, 2r).to_a.map(&:to_s) << (2**64).step(2**64 + 2).to_a.map(&:to_s)
        res << (2**62).step(2**62 + 1, 1).to_a.map(&:to_s)
        res << ((2**62 - 1).step(2**62 + 1, 2**61) { |i| r << i.to_s }; r[-2..])
        return res
        """)
        assert self.unwrap(space, w_res) == [
            1, [1, 4, 7, 10], [10, 7, 4, 1], [1, 2, 3], [1.0, 1.5, 2.0], [1, 3, 5, 7],
            [1, 3, 5, 7], [1, 2], [1, 4, 7, 10], 4, [], [1], [1, 3, 5], [1, 0, -1],
            [1.0, 2.0, 3.0], [1.0, 1.3, 1.6, 1.9], 4, 0, 0, [1.0],
            [1.0, 0.5, 0.0, -0.5, -1.0], 10, ["1", "3/1"],
            ["18446744073709551616", "18446744073709551617", "18446744073709551618"],
            ["4611686018427387904", "4611686018427387905"],
            ["4611686018427387903", "6917529027641081855"]]
        with self.raises(space, "ArgumentError", "step can't be 0"):
            space.execute("1.step(10, 0) { }")
        with self.raises(space, "ArgumentError", "step can't be 0"):
            space.execute("1.step(10, 0)")
        with self.raises(space, "ArgumentError", "step is given twice"):
            space.execute("1.step(10, 2, by: 3) { }")
        with self.raises(space, "ArgumentError", "to is given twice"):
            space.execute("1.step(10, to: 3) { }")
        with self.raises(space, "ArgumentError"):
            space.execute("1.step('a') { }")
        with self.raises(space, "ArgumentError"):
            space.execute("1.step(10, 'a') { }")

    def test_overflow_boundaries(self, space):
        from topaz.objects.intobject import W_FixnumObject

        values = [-sys.maxint - 1, -sys.maxint, -1, 0, 1, sys.maxint]
        for name, op in [("+", operator.add), ("-", operator.sub),
                         ("*", operator.mul)]:
            for left in values:
                for right in values:
                    expected = op(long(left), long(right))
                    w_result = space.send(space.newint(left), name,
                                          [space.newint(right)])
                    assert space.bigint_w(w_result).tolong() == expected
                    assert isinstance(w_result, W_FixnumObject) == (
                        -sys.maxint - 1 <= expected <= sys.maxint)

    def test_left_shift_boundaries(self, space):
        from topaz.objects.intobject import W_FixnumObject

        for value in [-sys.maxint - 1, -1, 0, 1, sys.maxint]:
            for shift in [0, 1, LONG_BIT - 1, LONG_BIT, LONG_BIT + 1]:
                expected = long(value) << shift
                w_result = space.send(space.newint(value), "<<",
                                      [space.newint(shift)])
                assert space.bigint_w(w_result).tolong() == expected
                assert isinstance(w_result, W_FixnumObject) == (
                    -sys.maxint - 1 <= expected <= sys.maxint)

    def test_class_is_integer(self, space):
        w_res = space.execute("""
        return [1.class, 1.instance_of?(Integer), 1.class.name,
                1.is_a?(Integer), Integer === 1]
        """)
        assert self.unwrap(space, w_res) == [
            space.w_integer, True, "Integer", True, True
        ]

    def test_integer_owns_builtin_methods(self, space):
        w_res = space.execute("""
        return [Integer.method_defined?(:+), Integer.instance_method(:+).owner,
                Integer.instance_methods(false).include?(:**)]
        """)
        assert self.unwrap(space, w_res) == [True, space.w_integer, True]

    def test_monkeypatch_integer_builtin(self, space):
        w_res = space.execute("""
        class Integer
          alias_method :orig_plus, :+
          def +(other)
            orig_plus(other).orig_plus(1)
          end
        end
        small = 1 + 1
        big = ((2 ** 70) + 1 - 2 ** 70) == 2
        class Integer
          remove_method :+
        end
        begin
          1 + 1
        rescue NoMethodError
          removed = true
        end
        class Integer
          alias_method :+, :orig_plus
        end
        return [small, big, removed, 1 + 1]
        """)
        assert self.unwrap(space, w_res) == [3, True, True, 2]

    def test_addition(self, space):
        w_res = space.execute("return 1 + 2")
        assert space.int_w(w_res) == 3

        w_res = space.execute("return 1 + 2.5")
        assert space.float_w(w_res) == 3.5

    def test_addition_ovf(self, space):
        w_res = space.execute("return (2 << (0.size * 8 - 3)) + (2 << (0.size * 8 - 3)) + (2 << (0.size * 8 - 3))")
        assert space.bigint_w(w_res) == rbigint.fromlong((2 << (LONG_BIT - 3)) * 3)

    def test_addition_bigint(self, space):
        w_res = space.execute("return 2 + %d" % (sys.maxint + 1))
        assert self.unwrap(space, w_res) == rbigint.fromlong(sys.maxint + 3)

    def test_multiplication(self, space):
        w_res = space.execute("return 2 * 3")
        assert space.int_w(w_res) == 6

    def test_multiplication_ovf(self, space):
        w_res = space.execute("return (2 << (0.size * 8 - 3)) * (2 << (0.size * 8 - 3))")
        assert space.bigint_w(w_res) == rbigint.fromlong((2 << (LONG_BIT - 3)) ** 2)

    def test_multiplication_bigint(self, space):
        w_res = space.execute("return 1 * %d" % (sys.maxint + 1))
        assert self.unwrap(space, w_res) == rbigint.fromlong(sys.maxint + 1)

    def test_subtraction(self, space):
        w_res = space.execute("return 2 - 3")
        assert space.int_w(w_res) == -1

        w_res = space.execute("return 2 - 3.5")
        assert space.float_w(w_res) == -1.5

    def test_subtraction_ovf(self, space):
        w_res = space.execute("return 0 - (2 << (0.size * 8 - 3)) - (2 << (0.size * 8 - 3)) - (2 << (0.size * 8 - 3))")
        assert space.bigint_w(w_res) == rbigint.fromlong((2 << (LONG_BIT - 3)) * -3)

    def test_substraction_bigint(self, space):
        w_res = space.execute("return 1 - %d" % (sys.maxint + 1))
        assert self.unwrap(space, w_res) == 1 - sys.maxint - 1

    def test_division(self, space):
        w_res = space.execute("return 3 / 5")
        assert space.int_w(w_res) == 0
        w_res = space.execute("return 3 / 5.0")
        assert space.float_w(w_res) == 0.6
        w_res = space.execute("return 3 / (0.0 / 0.0)")
        assert math.isnan(space.float_w(w_res))
        w_res = space.execute("return 3 / (1.0 / 0.0)")
        assert space.float_w(w_res) == 0.0
        w_res = space.execute("return 3 / (1.0 / -0.0)")
        assert space.float_w(w_res) == -0.0

    def test_div(self, space):
        w_res = space.execute("return 3.div(5)")
        assert space.int_w(w_res) == 0
        w_res = space.execute("return 3.div(5.0)")
        assert space.int_w(w_res) == 0
        with self.raises(space, "ZeroDivisionError", "divided by 0"):
            space.execute("return 3.div(0)")
        with self.raises(space, "FloatDomainError", "NaN"):
            space.execute("return 3.div(0.0 / 0.0)")

    def test_modulo(self, space):
        w_res = space.execute("return 5 % 2")
        assert space.int_w(w_res) == 1

    def test_left_shift(self, space):
        w_res = space.execute("return 3 << 4")
        assert space.int_w(w_res) == 48
        w_res = space.execute("return 48 << -4")
        assert space.int_w(w_res) == 3

    def test_left_shift_ovf(self, space):
        w_res = space.execute("return 4 << 90")
        assert space.bigint_w(w_res) == rbigint.fromlong(4951760157141521099596496896)
        w_res = space.execute("return %d << 2" % sys.maxint)
        assert self.unwrap(space, w_res) == rbigint.fromlong(sys.maxint << 2)
        w_res = space.execute("return 4 << -90")
        assert space.int_w(w_res) == 0

    def test_and(self, space):
        w_res = space.execute("return 12 & 123")
        assert space.int_w(w_res) == 8

    def test_xor(self, space):
        w_res = space.execute("return 12 ^ 15")
        assert space.int_w(w_res) == 3

    def test_or(self, space):
        w_res = space.execute("return 16 | 7")
        assert space.int_w(w_res) == 23
        w_res = space.execute("return 7 | 3")
        assert space.int_w(w_res) == 7

    def test_equal(self, space):
        w_res = space.execute("return 1 == 1")
        assert w_res is space.w_true
        w_res = space.execute("""
        class A
          def ==(o); 'hi'; end
        end
        return 1 == A.new
        """)
        assert space.str_w(w_res) == 'hi'
        w_res = space.execute("return 1 == '1'")
        assert w_res is space.w_false

    def test_not_equal(self, space):
        w_res = space.execute("return 1 != 1")
        assert w_res is space.w_false
        w_res = space.execute("return 1 != '1'")
        assert w_res is space.w_true
        w_res = space.execute("""
        class A
          def ==(o); 'hi'; end
        end
        return 1 != A.new
        """)
        assert w_res is space.w_false

    def test_less(self, space):
        w_res = space.execute("return 1 < 2")
        assert w_res is space.w_true
        w_res = space.execute("return 1 < 1.2")
        assert w_res is space.w_true

    def test_less_equal(self, space):
        assert space.execute("return 1 <= 2") is space.w_true
        assert space.execute("return 1 <= 1") is space.w_true
        assert space.execute("return 1 <= 1.1") is space.w_true
        assert space.execute("return 1 <= 0.9") is space.w_false
        with self.raises(space, "ArgumentError", "comparison of Integer with String failed"):
            space.execute("1 <= '1.1'")
        with self.raises(space, "ArgumentError", "comparison of Integer with String failed"):
            space.execute("1 <= 'a'")

    def test_greater(self, space):
        w_res = space.execute("return 1 > 2")
        assert w_res is space.w_false

    def test_greater_equal(self, space):
        w_res = space.execute("return 5 >= 4")
        assert w_res is space.w_true

    def test_times(self, space):
        w_res = space.execute("""
        res = []
        3.times do |x|
          res << x
        end
        return res
        """)
        assert self.unwrap(space, w_res) == [0, 1, 2]

    def test_upto(self, space):
        w_res = space.execute("""
        res = []
        3.upto(6) do |x|
          res << x
        end
        return res
        """)
        assert self.unwrap(space, w_res) == [3, 4, 5, 6]

    def test_comparator_lt(self, space):
        w_res = space.execute("return 1 <=> 2")
        assert space.int_w(w_res) == -1

    def test_comparator_eq(self, space):
        w_res = space.execute("return 1 <=> 1")
        assert space.int_w(w_res) == 0

    def test_comparator_gt(self, space):
        w_res = space.execute("return 2 <=> 1")
        assert space.int_w(w_res) == 1

    def test_comparator_float(self, space):
        w_res = space.execute("return 1 <=> 1.1")
        assert space.int_w(w_res) == -1

    def test_comparator_other_type(self, space):
        w_res = space.execute("return 1 <=> '1'")
        assert w_res is space.w_nil

    def test_eqlp(self, space):
        w_res = space.execute("return 1.eql? 1.0")
        assert w_res is space.w_false
        w_res = space.execute("return 1.eql? 1")
        assert w_res is space.w_true

    def test_to_i(self, space):
        w_res = space.execute("return [1.to_i, 1.to_int]")
        assert self.unwrap(space, w_res) == [1, 1]

    def test_nonzero(self, space):
        w_res = space.execute("return [2.nonzero?, 0.nonzero?]")
        assert self.unwrap(space, w_res) == [2, None]

    def test_object_id(self, space):
        w_res = space.execute("return 2.object_id, 2.object_id")
        id_1, id_2 = self.unwrap(space, w_res)
        assert id_1 == id_2

    def test___id__(self, space):
        w_res = space.execute("return 2.__id__, 2.__id__")
        id_1, id_2 = self.unwrap(space, w_res)
        assert id_1 == id_2

    def test_ivar(self, space):
        w_res = space.execute("""
        class Integer
          def set; @foo = -1; end
          def get; @foo; end
        end
        2.set
        return 2.get, 2.get, 3.get
        """)
        [x, y, z] = self.unwrap(space, w_res)
        assert x == y == -1
        assert z is None

    def test_freeze(self, space):
        w_res = space.execute("""
        res = [1.frozen?]
        1.freeze
        res << 1.frozen?
        res << 2.frozen?
        return res
        """)
        # Numbers are always frozen.
        assert self.unwrap(space, w_res) == [True, True, True]

    def test_succ(self, space):
        w_res = space.execute("return -1.succ")
        assert self.unwrap(space, w_res) == 0

        w_res = space.execute("return 7.succ")
        assert self.unwrap(space, w_res) == 8

    def test_zero(self, space):
        w_res = space.execute("return [0.zero?, 2.zero?]")
        assert self.unwrap(space, w_res) == [True, False]

    def test_even(self, space):
        w_res = space.execute("return [1.even?, -2.even?]")
        assert self.unwrap(space, w_res) == [False, True]

    def test_odd(self, space):
        w_res = space.execute("return [2.odd?, -1.odd?]")
        assert self.unwrap(space, w_res) == [False, True]

    def test_size(self, space):
        if sys.maxint == 2 ** 63 - 1:
            expected = 8
        elif sys.maxint == 2 ** 31 - 1:
            expected = 4
        else:
            raise NotImplementedError(sys.maxint)
        w_res = space.execute("return 1.size")
        assert space.int_w(w_res) == expected

    def test_chr(self, space):
        w_res = space.execute("return 65.chr")
        assert self.unwrap(space, w_res) == "A"
        with self.raises(space, "RangeError", "256 out of char range"):
            space.execute("256.chr")
        with self.raises(space, "RangeError", "-1 out of char range"):
            space.execute("-1.chr")
        w_res = space.execute("return 4.chr")
        assert self.unwrap(space, w_res) == "\x04"

    def test_pow(self, space):
        w_res = space.execute("return 2 ** 6")
        assert self.unwrap(space, w_res) == 64
        w_res = space.execute("return (2 ** -6) == Rational(1, 64)")
        assert w_res is space.w_true
        w_res = space.execute("return 4 ** 0.5")
        assert self.unwrap(space, w_res) == 2.0
        w_res = space.execute("return 4 ** -0.5")
        assert self.unwrap(space, w_res) == 0.5
        with self.raises(space, "TypeError", "String can't be coerced into Integer"):
            space.execute("2 ** 'hallo'")

    def test_step(self, space):
        w_res = space.execute("""
        res = []
        1.step(4) { |i| res << i }
        return res
        """)
        assert self.unwrap(space, w_res) == [1, 2, 3, 4]
        w_res = space.execute("""
        res = []
        1.step(4.1) { |i| res << i }
        return res
        """)
        assert self.unwrap(space, w_res) == [1.0, 2.0, 3.0, 4.0]
        w_res = space.execute("""
        res = []
        1.step(10, 2) { |i| res << i }
        return res
        """)
        assert self.unwrap(space, w_res) == [1, 3, 5, 7, 9]
        w_res = space.execute("""
        res = []
        1.step(2, 0.6) { |i| res << i }
        return res
        """)
        assert self.unwrap(space, w_res) == [1.0, 1.6]
