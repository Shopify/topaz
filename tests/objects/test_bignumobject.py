import operator
import sys

from rpython.rlib.rbigint import rbigint

from ..base import BaseTopazTest


class TestBignumObject(BaseTopazTest):
    def test_gcd(self, space):
        w_res = space.execute("""
        return [(2**70).gcd(2**65), (-2**70).gcd(-2**71), (2**64).gcd(2**64),
                (2**100 * 6).gcd(2**100 * 4), (2**70).gcd(6), 6.gcd(2**70)].map(&:to_s)
        """)
        assert self.unwrap(space, w_res) == [
            str(2 ** 65), str(2 ** 70), str(2 ** 64), str(2 ** 101), "2", "2"]
        with self.raises(space, "TypeError"):
            space.execute("(2**70).gcd(1.5)")

    def test_mixed_integer_operations(self, space):
        from topaz.objects.bignumobject import W_BignumObject
        from topaz.objects.intobject import W_FixnumObject

        # Include small values stored as bignums (e.g. produced by coerce),
        # cancellation back into a fixnum, and the minimum machine integer.
        big_values = [0L, 7L, long(sys.maxint) + 1, -(long(sys.maxint) + 2),
                      2L ** 130 + 5, -(2L ** 130 + 5)]
        small_values = [-sys.maxint - 1, -7, -1, 0, 1, 7, sys.maxint]
        for name, op in [("+", operator.add), ("-", operator.sub),
                         ("*", operator.mul), ("&", operator.and_),
                         ("|", operator.or_), ("^", operator.xor)]:
            for big in big_values:
                w_big = W_BignumObject(space, rbigint.fromlong(big))
                for small in small_values:
                    w_small = space.newint(small)
                    for left, right, w_left, w_right in [
                            (big, small, w_big, w_small),
                            (small, big, w_small, w_big)]:
                        expected = op(long(left), long(right))
                        w_result = space.send(w_left, name, [w_right])
                        assert space.bigint_w(w_result).tolong() == expected
                        assert isinstance(w_result, W_FixnumObject) == (
                            -sys.maxint - 1 <= expected <= sys.maxint)

    def test_mixed_division_and_comparison(self, space):
        from topaz.objects.bignumobject import W_BignumObject

        for big in [0L, 7L, 2L ** 130 + 5, -(2L ** 130 + 5)]:
            w_big = W_BignumObject(space, rbigint.fromlong(big))
            for small in [-sys.maxint - 1, -7, -1, 0, 1, 7, sys.maxint]:
                w_small = space.newint(small)
                assert space.is_true(space.send(w_big, "==", [w_small])) == (big == small)
                assert space.int_w(space.send(w_big, "<=>", [w_small])) == cmp(big, small)
                if small == 0:
                    for name in ["/", "%", "divmod"]:
                        with self.raises(space, "ZeroDivisionError", "divided by 0"):
                            space.send(w_big, name, [w_small])
                    continue
                w_div = space.send(w_big, "/", [w_small])
                w_mod = space.send(w_big, "%", [w_small])
                assert space.bigint_w(w_div).tolong() == big // small
                assert space.int_w(w_mod) == big % small
                results = space.listview(space.send(w_big, "divmod", [w_small]))
                assert [space.bigint_w(w).tolong() for w in results] == list(divmod(big, small))

    def test_mixed_to_int_coercion(self, space):
        w_res = space.execute("""
        class SmallOperand
          def to_int; 7; end
        end
        class BigOperand
          def to_int; 2 ** 100; end
        end
        big = 2 ** 100
        small = SmallOperand.new
        other = BigOperand.new
        return [big + small == big + 7, big - small == big - 7,
                big * small == big * 7, big & small == 0,
                big | small == big + 7, big ^ small == big + 7,
                big == other, (big <=> small) == 1,
                big + other == big * 2]
        """)
        assert self.unwrap(space, w_res) == [True] * 9

    def test_class_is_integer(self, space):
        w_res = space.execute("""
        big = 2 ** 70
        return [big.class, big.instance_of?(Integer), big.class.name,
                defined?(Bignum), defined?(Fixnum)]
        """)
        assert self.unwrap(space, w_res) == [
            space.w_integer, True, "Integer", None, None
        ]

    def test_plus(self, space):
        w_res = space.execute("return 18446744073709551628 + 9")
        assert space.bigint_w(w_res) == rbigint.fromlong(18446744073709551637)

    def test_sub(self, space):
        w_res = space.execute("return 18446744073709551628 - 18446744073709551658")
        assert space.bigint_w(w_res) == rbigint.fromint(-30)

    def test_neg(self, space):
        w_res = space.execute("return -(18446744073709551628)")
        assert space.bigint_w(w_res) == rbigint.fromlong(-18446744073709551628)

    def test_and(self, space):
        w_res = space.execute("return 18446744073709551628 & 18446744073709551658")
        assert space.bigint_w(w_res) == rbigint.fromlong(18446744073709551624)

    def test_xor(self, space):
        w_res = space.execute("return 18446744073709551628 ^ 18446744073709551658")
        assert space.bigint_w(w_res) == rbigint.fromint(38)

    def test_eq(self, space):
        w_res = space.execute("return 18446744073709551628 == 18446744073709551628")
        assert w_res is space.w_true
        w_res = space.execute("return 18446744073709551628 == 18446744073709551629")
        assert w_res is space.w_false

    def test_comparator(self, space):
        w_res = space.execute("return 18446744073709551628 <=> 2")
        assert space.int_w(w_res) == 1

    def test_hash(self, space):
        w_res = space.execute("return 18446744073709551628.hash == 18446744073709551628.hash")
        assert w_res is space.w_true
        w_res = space.execute("return 18446744073709551628.hash == 18446744073709551658.hash")
        assert w_res is space.w_false

    def test_coerce(self, space):
        w_res = space.execute("return 18446744073709551628.coerce 12")
        assert self.unwrap(space, w_res) == [rbigint.fromint(12), rbigint.fromlong(18446744073709551628)]

        w_res = space.execute("return 18446744073709551628.coerce 18446744073709551628")
        assert self.unwrap(space, w_res) == [rbigint.fromlong(18446744073709551628), rbigint.fromlong(18446744073709551628)]

        with self.raises(space, "TypeError", "can't coerce String to Integer"):
            space.execute("18446744073709551628.coerce 'hello'")

    def test_to_f(self, space):
        w_res = space.execute("return 18446744073709551628.to_f")
        assert space.float_w(w_res) == 1.8446744073709552e+19

    def test_pow(self, space):
        w_res = space.execute("return 18446744073709551628 ** 2")
        assert self.unwrap(space, w_res) == rbigint.fromlong(340282366920938463906096465200797450384)
        w_res = space.execute("return 18446744073709551628 ** -2")
        assert self.unwrap(space, w_res) == 1.0 / 340282366920938463906096465200797450384
        w_res = space.execute("return 18446744073709551628 ** 0.5")
        assert self.unwrap(space, w_res) == 4294967296.0
        w_res = space.execute("return 18446744073709551628 ** -0.5")
        assert self.unwrap(space, w_res) == 2.3283064365386963e-10
        with self.raises(space, "TypeError", "String can't be coerced into Integer"):
            space.execute("18446744073709551628 ** 'hallo'")
