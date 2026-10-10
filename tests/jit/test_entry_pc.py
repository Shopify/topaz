from .base import BaseJITTest


class TestEntryPC(BaseJITTest):
    def test_default_entries_and_backtraces_after_warmup(self, topaz, tmpdir):
        self.run(topaz, tmpdir, '''
          def mark(n); $seen << n; n; end
          def f(a = mark(1), b = mark(2))
            raise 'expected failure' if a == -1
            a + b
          end
          body = lambda { |a = mark(1), b = mark(2)| a + b }
          class EntryTarget
            define_method(:g) { |a = mark(1), b = mark(2)| a + b }
          end
          target = EntryTarget.new
          i = 0
          while i < 4000
            $seen = []
            raise 'supplied method' unless f(10, 20) == 30
            raise 'supplied lambda' unless body.call(10, 20) == 30
            raise 'supplied define_method' unless target.g(10, 20) == 30
            raise 'defaults ran' unless $seen == []
            if i == 3999
              raise 'method defaults' unless f == 3
              raise 'lambda defaults' unless body.call(10) == 12
              raise 'define_method defaults' unless target.g == 3
              raise 'wrong defaults' unless $seen == [1, 2, 2, 1, 2]
              begin
                call_line = __LINE__ + 1
                f(-1, 0)
              rescue RuntimeError => e
                raise 'wrong call site' unless e.backtrace[1].include?(":#{call_line}:")
              end
            end
            i += 1
          end
        ''')

    def test_fiber_entry_handoff(self, topaz, tmpdir):
        self.run(topaz, tmpdir, '''
          def mark(n)
            $seen << n
            Fiber.new { |x = 99| x }.resume(n)
          end
          def make_fiber
            Fiber.new do |a = mark(1), b = mark(2)|
              Fiber.yield([a, b])
              [a, b]
            end
          end
          class Arguments
            def to_ary
              Fiber.new { |x = 99| x }.resume(1)
              [10, 20]
            end
          end
          $seen = []
          f = make_fiber
          raise 'supplied' unless f.resume(10, 20) == [10, 20]
          raise 'supplied defaults ran' unless $seen == []
          raise 'resume' unless f.resume(99) == [10, 20]
          f = make_fiber
          raise 'partial' unless f.resume(10) == [10, 2]
          raise 'partial defaults' unless $seen == [2]
          f = make_fiber
          raise 'omitted' unless f.resume == [1, 2]
          raise 'omitted defaults' unless $seen == [2, 1, 2]
          f = make_fiber
          raise 'coercion handoff' unless f.resume(Arguments.new) == [10, 20]
        ''')
