import pytest

from tests.base import BaseTopazTest


class TestStableSuper(BaseTopazTest):
    @pytest.mark.parametrize('definition', [
        'def f; %s; end', 'define_method(:f) { %s }'])
    def test_prepend_same_module_during_active_call(self, space, definition):
        body = '''
          unless $changed
            $changed = true
            User.prepend(Repeat)
          end
          [:repeat] + super()
        '''
        result = space.execute('''
          module Repeat; %s; end
          class Base; def f; [:base]; end; end
          class User < Base; include Repeat; end
          return User.new.f
        ''' % (definition % body))
        assert self.unwrap(space, result) == ['repeat', 'base']

    @pytest.mark.parametrize('definition', [
        'def f; %s; end', 'define_method(:f) { %s }'])
    def test_prepend_same_module_after_block_capture(self, space, definition):
        result = space.execute('''
          module Repeat; %s; end
          class Base; def f; [:base]; end; end
          class User < Base; include Repeat; end
          saved = User.new.f
          User.prepend(Repeat)
          result = saved.call
          return result.kind_of?(Array) ? result : [:wrong_target]
        ''' % (definition % 'proc { super() }'))
        assert self.unwrap(space, result) == ['base']

    @pytest.mark.parametrize('capture', [
        'object.method(:f)', 'User.instance_method(:f).bind(object)'])
    def test_bound_method_retains_selected_ancestor(self, space, capture):
        result = space.execute('''
          module Repeat; def f; [:repeat] + super; end; end
          class Base; def f; [:base]; end; end
          class User < Base; include Repeat; end
          object = User.new
          saved = %s
          User.prepend(Repeat)
          return saved.call
        ''' % capture)
        assert self.unwrap(space, result) == ['repeat', 'base']

    def test_prepend_before_active_class_method(self, space):
        result = space.execute('''
          module Before; def f; [:before] + super; end; end
          class Base; def f; [:base]; end; end
          class User < Base
            def f
              self.class.prepend(Before)
              [:user] + super
            end
          end
          return User.new.f
        ''')
        assert self.unwrap(space, result) == ['user', 'base']

    def test_late_include_after_captured_entry_is_visible(self, space):
        result = space.execute('''
          module After; def f; [:after] + super; end; end
          module Repeat; def f; proc { super() }; end; end
          class Base; def f; [:base]; end; end
          class User < Base; include Repeat; end
          saved = User.new.f
          Repeat.include(After)
          return saved.call
        ''')
        assert self.unwrap(space, result) == ['after', 'base']

    @pytest.mark.parametrize('capture', [
        'User.instance_method(:f)', 'object.method(:f).unbind'])
    def test_unbound_method_selects_current_entry_when_bound(self, space, capture):
        result = space.execute('''
          module Repeat; def f; [:repeat] + super; end; end
          class Base; def f; [:base]; end; end
          class User < Base; include Repeat; end
          object = User.new
          saved = %s
          User.prepend(Repeat)
          return saved.bind(object).call
        ''' % capture)
        assert self.unwrap(space, result) == ['repeat', 'repeat', 'base']

    def test_defined_super_uses_captured_entry(self, space):
        result = space.execute('''
          module Repeat
            def f; proc { defined?(super) }; end
          end
          class User; include Repeat; end
          saved = User.new.f
          User.prepend(Repeat)
          return saved.call
        ''')
        assert result is space.w_nil

    def test_late_prepend_in_included_module_preserves_active_entry(self, space):
        result = space.execute('''
          module Before; def f; [:before] + super; end; end
          module Repeat
            def f
              Repeat.prepend(Before)
              [:repeat] + super
            end
          end
          class Base; def f; [:base]; end; end
          class User < Base; include Repeat; end
          return User.new.f
        ''')
        assert self.unwrap(space, result) == ['repeat', 'base']
