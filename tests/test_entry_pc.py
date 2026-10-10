import pytest

from tests.base import BaseTopazTest


class TestEntryPC(BaseTopazTest):
    @pytest.mark.parametrize('definition, call', [
        ('def subject(a = mark(1), b = mark(2), k: mark(3)); [a, b, k]; end', 'subject'),
        ('subject = lambda { |a = mark(1), b = mark(2), k: mark(3)| [a, b, k] }', 'subject.call'),
        ('subject = proc { |a = mark(1), b = mark(2), k: mark(3)| [a, b, k] }', 'subject.call'),
        ('class EntryTarget; define_method(:subject) { |a = mark(1), b = mark(2), k: mark(3)| [a, b, k] }; end; target = EntryTarget.new', 'target.subject'),
    ])
    def test_default_prologue_entry(self, space, definition, call):
        result = space.execute('''
          $seen = []
          def mark(n); $seen << n; n; end
          %s
          return [%s(), %s(10), %s(10, 20, k: 30), $seen]
        ''' % (definition, call, call, call))
        assert self.unwrap(space, result) == [[1, 2, 3], [10, 2, 3], [10, 20, 30], [1, 2, 3, 2, 3]]

    @pytest.mark.parametrize('args, expected, seen', [
        ('', [1, 2], [1, 2]), ('10', [10, 2], [2]), ('10, 20', [10, 20], [])])
    def test_fiber_entry_and_resumption(self, space, args, expected, seen):
        result = space.execute('''
          $seen = []
          def mark(n)
            $seen << n
            Fiber.new { |x = 99| x }.resume(n)
          end
          f = Fiber.new do |a = mark(1), b = mark(2)|
            Fiber.yield([a, b])
            [a, b]
          end
          first = f.resume(%s)
          second = f.resume(99)
          return [first, second, $seen]
        ''' % args)
        assert self.unwrap(space, result) == [expected, expected, seen]

    def test_fiber_argument_coercion_can_resume_another_fiber(self, space):
        result = space.execute('''
          class FiberArguments
            def to_ary
              Fiber.new { |x = 99| x }.resume(1)
              [10, 20]
            end
          end
          f = Fiber.new { |a = 1, b = 2| [a, b] }
          return f.resume(FiberArguments.new)
        ''')
        assert self.unwrap(space, result) == [10, 20]
