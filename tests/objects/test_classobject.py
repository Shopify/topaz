import pytest
from ..base import BaseTopazTest


class TestClassObject(BaseTopazTest):
    @pytest.mark.parametrize("change, expected", [
        ("def CacheParent.f; 2; end", 2),
        ("CacheParent.singleton_class.send(:remove_method, :f)", 0),
        ("CacheParent.singleton_class.prepend(CacheOverride)", 3),
    ])
    def test_inherited_class_method_cache_invalidation(self, space, change, expected):
        w_res = space.execute("""
        module CacheOverride; def f; 3; end; end
        class CacheRoot; def self.f; 0; end; end
        class CacheParent < CacheRoot; def self.f; 1; end; end
        class CacheChild < CacheParent; end
        class CacheGrandchild < CacheChild; end
        before = CacheGrandchild.f
        %s
        return [before, CacheGrandchild.f]
        """ % change)
        assert self.unwrap(space, w_res) == [1, expected]

    def test_inherited_class_method_cached_miss(self, space):
        w_res = space.execute("""
        class CacheParent; end
        class CacheChild < CacheParent; end
        before = CacheChild.respond_to?(:added)
        def CacheParent.added; 2; end
        return [before, CacheChild.respond_to?(:added), CacheChild.added]
        """)
        assert self.unwrap(space, w_res) == [False, True, 2]

    def test_inherited_class_method_undef_invalidates_cache(self, space):
        w_res = space.execute("""
        class CacheParent; def self.f; 1; end; end
        class CacheChild < CacheParent; end
        before = CacheChild.f
        CacheParent.singleton_class.send(:undef_method, :f)
        return [before, CacheChild.respond_to?(:f)]
        """)
        assert self.unwrap(space, w_res) == [1, False]

    def test_instance_singleton_inherited_method_cache(self, space):
        w_res = space.execute("""
        class CacheClass; def f; 1; end; end
        obj = CacheClass.new
        def obj.g; end
        before = obj.f
        class CacheClass; def f; 2; end; end
        return [before, obj.f]
        """)
        assert self.unwrap(space, w_res) == [1, 2]

    def test_singleton_dependencies_do_not_call_inherited(self, space):
        w_res = space.execute("""
        class CacheParent
          @children = []
          def self.inherited(child); @children << child; end
          def self.children; @children; end
        end
        class CacheChild < CacheParent; end
        obj = CacheParent.new
        def obj.f; end
        return [CacheParent.children == [CacheChild],
                CacheParent.subclasses == [CacheChild],
                CacheParent.singleton_class.subclasses]
        """)
        assert self.unwrap(space, w_res) == [True, True, []]

    def test_bootstrap_singleton_dependency(self, space):
        assert space.w_basicobject.klass in space.w_class.descendants_w()

    def test_name(self, space):
        space.execute("Class")

    def test_generated_subclass(self, space):
        w_res = space.execute("""
        class Foo
          class Bar
            class Baz
            end
          end
        end
        return Foo::Bar::Baz.name
        """)
        assert space.str_w(w_res) == "Foo::Bar::Baz"

    def test_to_s(self, space):
        w_res = space.execute("return 1.class.to_s")
        assert space.str_w(w_res) == "Integer"

        w_res = space.execute("return 1.class.class.to_s")
        assert space.str_w(w_res) == "Class"

    def test_anon_class_to_s(self, space):
        w_res = space.execute("return Class.new.to_s")
        assert space.str_w(w_res).startswith("#<Class:0x")

        w_res = space.execute("return Class.new.new.to_s")
        assert space.str_w(w_res).startswith("#<#<Class:0x")

    @pytest.mark.xfail
    def test_singletonclass_to_s(self, space):
        w_res = space.execute("Class.new.singleton_class.to_s")
        assert space.str_w(w_res).startswith("#<Class:#<Class:0x")

    def test_anon_class_name(self, space):
        w_res = space.execute("return Class.new.name")
        assert w_res is space.w_nil

    def test_anon_class_method_missing_raises(self, space):
        with self.raises(space, "NoMethodError"):
            space.execute("""
            class A; end
            Class.new.does_not_exist
            """)

    def test_singletonclass_name(self, space):
        w_res = space.execute("Class.new.singleton_class.name")
        assert w_res is space.w_nil

    def test_class_new(self, space):
        w_res = space.execute("return Class.new.superclass.name")
        assert space.str_w(w_res) == "Object"
        w_res = space.execute("return Class.new(String).superclass.name")
        assert space.str_w(w_res) == "String"

    def test_new(self, space):
        w_res = space.execute("""
        class X
        end

        return X.new
        """)
        w_cls = space.w_object.constants_w["X"]
        assert space.getclass(w_res) is w_cls

        w_res = space.execute("""
        class X
          def m
            self
          end
        end

        x = X.new
        return [x, x.m]
        """)

        [w_x, w_xm] = space.listview(w_res)
        assert w_xm is w_x

    def test_superclass(self, space):
        w_res = space.execute("return Object.superclass")
        assert w_res is space.w_basicobject
        w_res = space.execute("return BasicObject.superclass")
        assert w_res is space.w_nil

    def test_attr_accessor(self, space):
        w_res = space.execute("""
        class X
          attr_accessor :a, :b, :c
          def initialize a
            @a = a
            self.b = 25
          end
        end

        x = X.new(3)
        orig_a = x.a
        x.a = 5
        return [orig_a, x.a, x.b]
        """)
        assert [space.int_w(w_x) for w_x in space.listview(w_res)] == [3, 5, 25]

    def test_attr_reader(self, space):
        w_res = space.execute("""
        class X
          attr_reader :a
          def initialize
            @a = 5
          end
        end
        return X.new.a
        """)
        assert space.int_w(w_res) == 5
