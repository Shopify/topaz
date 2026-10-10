import pytest

from rpython.rlib.rarithmetic import LONG_BIT

from .base import BaseJITTest


class TestKeywordSlots(BaseJITTest):
    @pytest.mark.parametrize('count', [LONG_BIT - 1, LONG_BIT])
    def test_high_bitmap_bits(self, topaz, tmpdir, count):
        parameters = ', '.join('k%d: %d' % (i, i) for i in range(count))
        self.run(topaz, tmpdir, '''
          def f(%s)
            [k0, k%d]
          end
          i = 0
          while i < 3000
            raise "wrong supplied values" unless f(k0: nil, k%d: false) == [nil, false]
            raise "wrong defaults" unless f == [0, %d]
            i += 1
          end
        ''' % (parameters, count - 1, count - 1, count - 1))

    def test_limit_is_rescuable_syntax_error(self, topaz, tmpdir):
        parameters = ', '.join('k%d: 0' % i for i in range(LONG_BIT + 1))
        self.run(topaz, tmpdir, '''
          begin
            eval("def f(%s); end")
            raise "oversized bitmap was accepted"
          rescue SyntaxError => e
            raise "wrong error" unless e.message ==
              "too many keyword arguments with defaults (maximum %d)"
          end
        ''' % (parameters, LONG_BIT))

    def test_keyword_prologue_and_guard_failure(self, topaz, tmpdir):
        self.run(topaz, tmpdir, '''
          def f(n, a = 3, k: 4, **rest)
            i = 0
            while i < n
              i += 1
            end
            [i, a, k, rest]
          end
          i = 0
          while i < 3000
            if i == 2999
              raise "wrong omission" unless f(100) == [100, 3, 4, {}]
            else
              raise "wrong supplied value" unless f(100, k: nil, extra: 7) ==
                [100, 3, nil, {extra: 7}]
            end
            i += 1
          end
        ''')
