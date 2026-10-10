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
