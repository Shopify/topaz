import pytest

from topaz.objects.moduleobject import W_Autoload
from .base import BaseTopazTest


class TestModuleMutations(BaseTopazTest):
    @pytest.mark.parametrize("body", [
        "[:m] + super",
        "[:m] + super()",
        "[:m] + super(*[])",
        "[:m] + proc { super() }.call",
    ])
    @pytest.mark.parametrize("definition", [
        "def f; %s; end", "define_method(:f) { %s }",
        "def f; %s; end; define_method(:f, instance_method(:f))",
    ])
    @pytest.mark.parametrize("hierarchy", [
        "class User < Base; include Middle; include Repeat; end; Middle.include(Repeat)",
        "class Parent < Base; include Repeat; end; "
        "class User < Parent; include Middle; prepend Repeat; end",
    ])
    def test_super_through_repeated_module(self, space, body, definition, hierarchy):
        # Bound the recursion so a broken lookup fails without a stack overflow.
        body = "$calls += 1; return [:cycle] if $calls > 5; " + body
        if "define_method" in definition and body.endswith("super"):
            body += "()"
        w_res = space.execute("""
        $calls = 0
        module Repeat; %s; end
        module Middle; def f; [:middle] + super; end; end
        class Base; def f; [:base]; end; end
        %s
        return User.new.f
        """ % (definition % body, hierarchy))
        assert self.unwrap(space, w_res) == ["m", "middle", "m", "base"]

    def test_saved_super_blocks_retain_separate_occurrences(self, space):
        w_res = space.execute("""
        module Repeat; def f; [:m, proc { super() }]; end; end
        module Middle; def f; [:middle, super]; end; end
        class Base; def f; [:base]; end; end
        class User < Base; include Middle; include Repeat; end
        Middle.include(Repeat)
        first = User.new.f
        middle = first[1].call
        second = middle[1]
        return [first[0], middle[0], second[0], second[1].call]
        """)
        assert self.unwrap(space, w_res) == ["m", "middle", "m", ["base"]]

    def test_defined_super_at_last_repeated_module(self, space):
        w_res = space.execute("""
        $calls = 0
        module Repeat
          def f
            $calls += 1
            return [:cycle] if $calls > 5
            [defined?(super)] + (defined?(super) ? super : [])
          end
        end
        module Middle; def f; super; end; end
        class User; include Middle; include Repeat; end
        Middle.include(Repeat)
        return User.new.f
        """)
        assert self.unwrap(space, w_res) == ["super", None]

    @pytest.mark.parametrize("use", ["include", "prepend"])
    @pytest.mark.parametrize("change", ["include", "prepend"])
    def test_late_ancestor_updates_existing_users(self, space, use, change):
        w_res = space.execute("""
        module LateInner; def f; :inner; end; end
        module LateOuter; def f; super; end; end
        module LateMiddle; include LateOuter; end
        class LateBase; def f; :base; end; end
        class LateClass < LateBase; %s LateMiddle; end
        obj = LateClass.new
        before = obj.f
        LateOuter.%s(LateInner)
        a = LateClass.ancestors
        return [before, obj.f, a.index(LateInner) - a.index(LateOuter)]
        """ % (use, change))
        assert self.unwrap(space, w_res) == ["base", "inner", 1 if change == "include" else -1]

    def test_late_include_duplicate_order(self, space):
        w_res = space.execute("""
        module Shared; end
        module Outer; end
        class Before; include Outer; include Shared; end
        class After; include Shared; include Outer; end
        Outer.include(Shared)
        return [Before.ancestors.take(4), After.ancestors.take(3)].map { |a| a.map(&:name) }
        """)
        assert self.unwrap(space, w_res) == [
            ["Before", "Shared", "Outer", "Shared"], ["After", "Outer", "Shared"]]

    def test_successive_late_prepends_keep_order_and_do_not_repeat_hooks(self, space):
        w_res = space.execute("""
        $included_calls = 0
        module Outer
          def self.included(base); $included_calls += 1; end
          def f; [:outer] + super; end
        end
        module One; def f; [:one] + super; end; end
        module Two; def f; [:two] + super; end; end
        class Base; def f; [:base]; end; end
        class User < Base; include Outer; end
        Outer.prepend(One)
        Outer.prepend(Two)
        return [User.new.f, $included_calls]
        """)
        assert self.unwrap(space, w_res) == [["two", "one", "outer", "base"], 1]

    def test_shared_ancestor_lookup_respects_flattened_order(self, space):
        w_res = space.execute("""
        module Shared; def f; [:shared] + super; end; end
        module Left; include Shared; def f; [:left] + super; end; end
        module Right; include Shared; def f; [:right] + super; end; end
        class Base; def f; [:base]; end; end
        class User < Base; include Right; include Left; end
        return User.new.f
        """)
        assert self.unwrap(space, w_res) == ["left", "right", "shared", "base"]

    def test_define_method_initializer_keeps_super_owner(self, space):
        w_res = space.execute("""
        class Base; def initialize; @value = 3; end; end
        class User < Base
          define_method(:initialize) { super() }
          attr_reader :value
        end
        return User.new.value
        """)
        assert space.int_w(w_res) == 3

    def test_clone_preserves_singleton_prepends(self, space):
        w_res = space.execute("""
        module Pre; def f; [:pre] + super; end; end
        class Base; def f; [:base]; end; end
        obj = Base.new
        def obj.f; [:own] + super; end
        obj.singleton_class.prepend(Pre)
        copy = obj.clone
        before = copy.f
        module Pre; def f; [:changed] + super; end; end
        return [before, copy.f, obj.f]
        """)
        assert self.unwrap(space, w_res) == [
            ["pre", "own", "base"], ["changed", "own", "base"],
            ["changed", "own", "base"]]

    @pytest.mark.parametrize("copy_method", ["dup", "clone"])
    @pytest.mark.parametrize("definition", [
        "def f; 1; end", "attr_reader :f", "define_method(:f) { 1 }",
        "def helper; 1; end; define_method(:f, instance_method(:helper))",
    ])
    def test_copy_visibility_is_independent(self, space, copy_method, definition):
        w_res = space.execute("""
        module Vis; %s; end
        copy = Vis.%s
        copy.send(:private, :f)
        before = Vis.public_instance_methods(false).include?(:f)
        Vis.send(:protected, :f)
        return [before, copy.private_instance_methods(false).include?(:f),
                Vis.protected_instance_methods(false).include?(:f)]
        """ % (definition, copy_method))
        assert self.unwrap(space, w_res) == [True, True, True]

    @pytest.mark.parametrize("outcome", ["defined", "missing", "raises"])
    def test_autoload_versions_cover_temporary_writes(self, space, monkeypatch, outcome):
        w_mod = space.newmodule(None)
        w_autoload = W_Autoload(space, "unused")
        w_mod.set_const(space, "Value", w_autoload)
        old_version = w_mod.version
        versions = []

        def load(loader):
            assert w_mod.version is not old_version
            assert w_mod.find_local_const(space, "Value", autoload=False) is None
            versions.append(w_mod.version)
            if outcome == "raises":
                raise ValueError("autoload failed")
            if outcome == "defined":
                w_mod.set_const(space, "Value", space.newint(42))

        monkeypatch.setattr(W_Autoload, "load", load)
        if outcome == "raises":
            with pytest.raises(ValueError):
                w_mod.find_local_const(space, "Value")
            assert w_mod.find_local_const(space, "Value", autoload=False) is w_autoload
            assert w_mod.version is not versions[0]
        elif outcome == "defined":
            assert space.int_w(w_mod.find_local_const(space, "Value")) == 42
        else:
            assert w_mod.find_local_const(space, "Value") is None
            assert "Value" not in w_mod.constants_w

    def test_autoload_can_retry_after_exception(self, space, tmpdir):
        path = tmpdir.join("retry_autoload.rb")
        path.write("$attempts += 1; raise 'retry' if $attempts == 1; AutoRetry::Value = 42")
        w_res = space.execute("""
        $attempts = 0
        module AutoRetry; end
        AutoRetry.autoload(:Value, %r)
        begin
          AutoRetry::Value
        rescue RuntimeError
        end
        return [AutoRetry.autoload?(:Value).nil?, AutoRetry::Value, $attempts]
        """ % str(path))
        assert self.unwrap(space, w_res) == [False, 42, 2]
