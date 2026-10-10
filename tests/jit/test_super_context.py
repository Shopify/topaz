from tests.test_super_context import SUPER_CONTEXT_SOURCE
from .base import BaseJITTest


class TestSuperContext(BaseJITTest):
    def test_escaped_super_context_after_redefinition(self, topaz, tmpdir):
        self.run(topaz, tmpdir, SUPER_CONTEXT_SOURCE + '''
          object = ContextChild.new
          saved_f = object.send(:f_alias, 2)
          saved_g = object.send(:g_alias, 3)
          i = 0
          while i < 5000
            if i == 4000
              class ContextParent
                def f(x = 0); 20 + x; end
                def g(x = 0); 200 + x; end
              end
            end
            expected_f = i < 4000 ? 12 : 22
            expected_g = i < 4000 ? 103 : 203
            raise 'wrong f' unless saved_f.call == expected_f
            raise 'wrong g' unless saved_g.call == expected_g
            raise 'wrong new f' unless object.f(2).call == expected_f
            raise 'wrong new g' unless object.g(3).call == expected_g
            i += 1
          end
        ''')

    def test_ancestor_mutation_after_warmup(self, topaz, tmpdir):
        traces = self.run(topaz, tmpdir, '''
          module StableMixin
            def f(change)
              if change && !$changed
                $changed = true
                StableUser.prepend(StableMixin)
              end
              1 + super(change)
            end
            define_method(:capture) { proc { super() } }
          end
          class StableBase
            def f(change); 10; end
            def capture; 20; end
          end
          class StableUser < StableBase; include StableMixin; end
          object = StableUser.new
          saved = object.capture
          bound = object.method(:f)
          i = 0
          while i < 10000
            raise 'warmup' unless object.f(false) == 11
            raise 'block warmup' unless saved.call == 20
            i += 1
          end
          raise 'active entry moved' unless object.f(true) == 11
          i = 0
          while i < 10000
            raise 'fresh lookup' unless object.f(false) == 12
            raise 'bound entry moved' unless bound.call(false) == 11
            raise 'block entry moved' unless saved.call == 20
            i += 1
          end
        ''')
        assert traces
