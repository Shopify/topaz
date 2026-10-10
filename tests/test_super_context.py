import pytest

from topaz.objects.functionobject import SuperContext
from tests.base import BaseTopazTest


SUPER_CONTEXT_SOURCE = '''
  class ContextParent
    def f(x = 0); 10 + x; end
    def g(x = 0); 100 + x; end
  end
  class ContextChild < ContextParent
    def f(x = 0); proc { super(x) }; end
    define_method(:g) { |x = 0| proc { super(x) } }
    alias_method :f_alias, :f
    alias_method :g_alias, :g
    private :f_alias, :g_alias
  end
'''


class TestSuperContext(BaseTopazTest):
    def test_fast_argument_path_captures_context(self, space):
        proc = space.execute('''
          class FastContextParent
            def f(x); 10 + x; end
          end
          class FastContextChild < FastContextParent
            def f(x); proc { super(x) }; end
          end
          return FastContextChild.new.f(3)
        ''')
        method = self.find_const(space, 'FastContextChild').find_method(space, 'f')
        assert method.bytecode.fast_arity == 1
        assert proc.super_context is method.super_context
        assert space.int_w(space.send(proc, 'call')) == 13

    @pytest.mark.parametrize('name, expected', [('f', 13), ('g', 103)])
    def test_calls_and_proc_copies_share_method_context(self, space, monkeypatch,
                                                       name, expected):
        space.execute(SUPER_CONTEXT_SOURCE)
        w_class = self.find_const(space, 'ContextChild')
        method = w_class.find_method(space, name)
        alias = w_class.find_method(space, name + '_alias')
        context = method.super_context
        assert context is alias.super_context
        assert context.w_owner is w_class
        assert context.name == (None if name == 'f' else 'g')
        w_receiver = space.send(w_class, 'new')

        def unexpected_context(self, owner, name):
            raise AssertionError('allocated super context during a call')

        monkeypatch.setattr(SuperContext, '__init__', unexpected_context)
        for unused in range(2):
            proc = space.send(w_receiver, name, [space.newint(3)])
            assert proc.super_context is context
            assert proc.copy(space).super_context is context
            assert proc.orphan_copy(space).super_context is context
            assert space.int_w(space.send(proc, 'call')) == expected

    def test_escaped_alias_blocks_survive_redefinition(self, space):
        result = space.execute(SUPER_CONTEXT_SOURCE + '''
          object = ContextChild.new
          f = object.send(:f_alias, 2)
          g = object.send(:g_alias, 3)
          bound = object.method(:g)
          class ContextChild
            def f; :replacement; end
            define_method(:g) { :replacement }
          end
          class ContextParent
            def f(x = 0); 20 + x; end
            def g(x = 0); 200 + x; end
          end
          return [f.call, g.call, bound.call(4).call]
        ''')
        assert self.unwrap(space, result) == [22, 203, 204]

    def test_reused_define_method_block_has_distinct_owners(self, space):
        w_module = space.execute('''
          ContextBody = proc { proc { 1 } }
          module ContextModule
            define_method(:f, ContextBody)
            class << self
              define_method(:f, ContextBody)
            end
          end
          return ContextModule
        ''')
        singleton = space.getsingletonclass(w_module)
        instance_context = w_module.find_method(space, 'f').super_context
        singleton_context = singleton.find_method(space, 'f').super_context
        assert instance_context.w_owner is w_module
        assert singleton_context.w_owner is singleton
        assert instance_context is not singleton_context
        assert instance_context.name == singleton_context.name == 'f'
