import pytest

from ..base import BaseTopazTest


class TestHashObject(BaseTopazTest):
    @pytest.mark.parametrize('method, other', [
        ('collect_concat', 'flat_map'), ('flat_map', 'collect_concat')])
    @pytest.mark.parametrize('singleton', [False, True])
    def test_flat_map_enumerator_keeps_method_name(self, space, method, other,
                                                  singleton):
        if singleton:
            setup = 'h = {a: 1}; def h.%s; [:wrong]; end' % other
        else:
            setup = '''class CustomHash < Hash
              def %s; [:wrong]; end
            end
            h = CustomHash.new; h[:a] = 1''' % other
        w_res = space.execute(setup + '''
          return h.%s.each { |key, value| [value] }
        ''' % method)
        assert self.unwrap(space, w_res) == [1]

    @pytest.mark.parametrize('method, other', [
        ('collect_concat', 'flat_map'), ('flat_map', 'collect_concat')])
    def test_flat_map_each_fallback_keeps_method_name(self, space, method, other):
        w_res = space.execute('''
          module Enumerable
            def %s; [:wrong]; end
          end
          class CustomHash < Hash
            def each; yield [:custom, 42]; end
          end
          return CustomHash.new.%s { |key, value| [value] }
        ''' % (other, method))
        assert self.unwrap(space, w_res) == [42]

    def test_flat_map_results_and_arguments(self, space):
        w_res = space.execute('''
        h = {a: 1, b: 2}
        converted = Object.new
        def converted.to_ary; [3, [4]]; end
        scalar = Object.new
        def scalar.to_ary; nil; end
        return [h.flat_map { |k, v| [v, [v]] },
                h.collect_concat { |pair| pair[1] },
                h.flat_map { |*args| [args.size, args[0].size] },
                h.flat_map { converted },
                h.flat_map { scalar }.all? { |v| v.equal?(scalar) },
                h.flat_map { nil }, {}.flat_map { raise 'empty' },
                h.flat_map.each { |k, v| [v] },
                h.collect_concat.each { |k, v| [v] }]
        ''')
        assert self.unwrap(space, w_res) == [
            [1, [1], 2, [2]], [1, 2], [1, 2, 1, 2],
            [3, [4], 3, [4]], True, [None, None], [], [1, 2], [1, 2]]

    @pytest.mark.parametrize('setup', [
        "h = {a: 1, b: 2, c: 3}",
        "h = {'a' => 1, 'b' => 2, 'c' => 3}",
        "h = {1 => 1, 2 => 2, 3 => 3}",
        "h = {'a' => 1, 'b' => 2, 'c' => 3}.compare_by_identity",
    ])
    def test_flat_map_mutation_and_transition(self, space, setup):
        w_res = space.execute('''
        %s
        keys = h.keys
        result = h.flat_map do |key, value|
          if value == 1
            h[Object.new]
            h[keys[1]] = 20
            h.delete(keys[2])
          end
          [keys.include?(key), value]
        end
        return result
        ''' % setup)
        assert self.unwrap(space, w_res) == [True, 1, True, 20]

    def test_flat_map_control_flow_and_conversion_error(self, space):
        w_res = space.execute('''
        def early_return
          {a: 1}.flat_map { return 7 }
        end
        bad = Object.new
        def bad.to_ary; 42; end
        error = begin
          {a: 1}.flat_map { bad }
          false
        rescue TypeError
          true
        end
        return [early_return, {a: 1}.flat_map { break 8 },
                {a: 1}.flat_map { next [9] },
                {a: 1}.flat_map(&lambda { |pair| [pair[1]] }), error]
        ''')
        assert self.unwrap(space, w_res) == [7, 8, [9], [1], True]

    def test_flat_map_overridden_each(self, space):
        w_res = space.execute('''
        class CustomHash < Hash
          def each
            yield [:custom, 42]
          end
        end
        h = {a: 1}
        def h.each
          yield [:singleton, 43]
        end
        return [CustomHash.new.flat_map { |k, v| [v] },
                h.collect_concat { |k, v| [v] }]
        ''')
        assert self.unwrap(space, w_res) == [[42], [43]]

    @pytest.mark.parametrize('stored_mutable', [False, True])
    @pytest.mark.parametrize('lookup_mutable', [False, True])
    def test_string_storage_callbacks(self, space, monkeypatch,
                                      stored_mutable, lookup_mutable):
        from topaz.objects.hashobject import StringDictStrategy, string_hash, string_eq

        def unexpected(*args):
            raise AssertionError('generic Hash callback')

        monkeypatch.setattr(space, 'hash_w', unexpected)
        monkeypatch.setattr(space, 'eq_w', unexpected)
        w_hash = space.newhash()
        keys = []
        for value in ['', 'abc', 'abd', '\x00\xff']:
            stored = space.newstr_fromstr(value)
            lookup = space.newstr_fromstr(value)
            if stored_mutable:
                stored.strategy.to_mutable(space, stored)
            if lookup_mutable:
                lookup.strategy.to_mutable(space, lookup)
            assert string_hash(stored) == string_hash(lookup)
            assert string_eq(stored, lookup)
            w_hash.method_subscript_assign(space, stored, space.newint(7))
            assert w_hash.strategy is space.fromcache(StringDictStrategy)
            assert space.int_w(w_hash.getitem(lookup)) == 7
            assert w_hash.contains(lookup)
            keys.append(lookup)
        assert not string_eq(keys[1], keys[2])
        assert not w_hash.contains(space.newstr_fromstr('missing'))
        assert space.int_w(w_hash.delete(keys[1])) == 7
        assert not w_hash.contains(keys[1])

    def test_string_storage_keys_and_mutation(self, space):
        from topaz.objects.hashobject import StringDictStrategy
        w_res = space.execute('''
        source = 'a'
        source << 'b'
        frozen = 'second'.freeze
        h = {source => 1, frozen => 2}
        stored = h.keys[0]
        result = [stored.equal?(source), stored.frozen?, h.keys[1].equal?(frozen)]
        source << 'c'
        result << h['ab'] << h[source]
        probe = 'a'
        probe << 'b'
        result << h[probe]
        probe[1] = 'c'
        result << h[probe]
        probe[1] = 'b'
        h[probe] = 3
        result << h.keys[0].equal?(stored) << h.keys << h.values
        return [result, h]
        ''')
        result, w_hash = space.listview(w_res)
        assert self.unwrap(space, result) == [False, True, True, 1, None, 1,
                                              None, True, ['ab', 'second'], [3, 2]]
        assert w_hash.strategy is space.fromcache(StringDictStrategy)

    def test_string_storage_custom_key_fallback(self, space):
        w_res = space.execute('''
        class StringAlias
          def hash; 'a'.hash; end
          def eql?(other); other == 'a'; end
        end
        class StringSubclass < String
          def hash; 'a'.hash; end
          def eql?(other); other == 'a'; end
        end
        result = []
        [StringAlias.new, StringSubclass.new('different')].each do |key|
          result << {'a' => 7}[key]
          result << {'a' => 7}.key?(key)
          result << {'a' => 7}.delete(key)
          h = {'a' => 7, 'b' => 8}
          original = h.keys[0]
          h[key] = 9
          result << h.keys << h.values << h.keys[0].equal?(original)
          result << {'a' => 7}.freeze[key]
        end
        return result
        ''')
        assert self.unwrap(space, w_res) == [7, True, 7, ['a', 'b'], [9, 8], True, 7] * 2

    def test_string_storage_subclass_starts_generic(self, space):
        from topaz.objects.hashobject import ObjectDictStrategy
        w_hash = space.execute('''
        class StringSubclass < String; end
        return {StringSubclass.new('a') => 1}
        ''')
        assert w_hash.strategy is space.fromcache(ObjectDictStrategy)

    def test_string_storage_mixed_insertion(self, space):
        from topaz.objects.hashobject import ObjectDictStrategy
        w_hash = space.execute("return {'a' => 1, 'b' => 2}")
        keys = w_hash.strategy.keys(w_hash.dict_storage)
        w_hash.setitem(space.newint(42), space.newint(3))
        assert w_hash.strategy is space.fromcache(ObjectDictStrategy)
        assert w_hash.strategy.keys(w_hash.dict_storage)[:2] == keys
        assert self.unwrap(space, space.send(w_hash, 'keys')) == ['a', 'b', 42]
        assert space.int_w(w_hash.getitem(space.newstr_fromstr('a'))) == 1

    def test_string_storage_copy_and_identity(self, space):
        from topaz.objects.hashobject import StringDictStrategy, IdentityDictStrategy
        w_hash = space.execute("return {'a' => 1, 'b' => 2}.dup.rehash")
        assert w_hash.strategy is space.fromcache(StringDictStrategy)
        w_copy = w_hash.copy_keywords(space)
        w_copy.delete(space.newstr_fromstr('a'))
        assert w_copy.size() == 1
        assert w_hash.size() == 2
        keys = w_hash.strategy.keys(w_hash.dict_storage)
        space.send(w_hash, 'compare_by_identity')
        assert w_hash.strategy is space.fromcache(IdentityDictStrategy)
        assert w_hash.strategy.keys(w_hash.dict_storage) == keys
        assert not w_hash.contains(space.newstr_fromstr('a'))
        assert w_hash.contains(keys[0])

    def test_string_storage_transition_during_iteration(self, space):
        w_res = space.execute('''
        h = {'a' => 1, 'b' => 2, 'c' => 3}
        seen = []
        h.each do |key, value|
          seen << [key, value]
          if key == 'a'
            h[Object.new]
            h['b'] = 20
            h.delete('c')
          end
        end
        h = {'a' => 1, 'b' => 2}
        stored = h.keys[1]
        iter = Topaz::HashIterator.new(h)
        first = iter.next
        h[:missing]
        h['b'] = 20
        last = iter.next
        return [seen, first, last, last[0].equal?(stored)]
        ''')
        assert self.unwrap(space, w_res) == [[['a', 1], ['b', 20]], ['a', 1], ['b', 20], True]

    def test_name(self, space):
        space.execute("Hash")

    def test_create(self, space):
        space.execute("{2 => 3, 4 => 5}")

    def test_subscript_create(self, space):
        w_res = space.execute("return Hash[].length")
        assert space.int_w(w_res) == 0

    def test_subscript_create_hash(self, space):
        w_res = space.execute("return Hash[{2 => 3}][2]")
        assert space.int_w(w_res) == 3

    def test_default_value(self, space):
        w_res = space.execute("""
        x = Hash.new 5
        return x[2]
        """)
        assert space.int_w(w_res) == 5
        w_res = space.execute("""
        x = Hash.new 5
        x[2] = 12
        return x[2]
        """)
        assert space.int_w(w_res) == 12
        w_res = space.execute("return Hash.new(2).default")
        assert space.int_w(w_res) == 2

        w_res = space.execute("""
        class Foo < Hash
          def default key
            key * 2
          end
        end

        return Foo.new[6]
        """)
        assert space.int_w(w_res) == 12

    def test_default_proc(self, space):
        w_res = space.execute("""
        x = Hash.new { |h, k| h[k + 2] = k }
        return [x[2], x[4]]
        """)
        assert self.unwrap(space, w_res) == [2, 2]

    def test_new(self, space):
        w_res = space.execute("return Hash.new.keys")
        assert self.unwrap(space, w_res) == []

    def test_lookup(self, space):
        w_res = space.execute("""
        x = {2 => 3}
        return x[2]
        """)
        assert self.unwrap(space, w_res) == 3

    def test_lookup_non_existing(self, space):
        w_res = space.execute("""
        x = {}
        return x[2]
        """)
        assert w_res is space.w_nil

    def test_clear(self, space):
        w_res = space.execute("""
        x = {2 => 3}
        x.clear
        return x.keys
        """)
        assert self.unwrap(space, w_res) == []

    def test_lookup_eql(self, space):
        w_res = space.execute("return {1 => 2}[1.0]")
        assert w_res is space.w_nil

    def test_fetch_existing(self, space):
        w_res = space.execute("return {'a' => 1}.fetch('a')")
        assert self.unwrap(space, w_res) == 1

    def test_fetch_non_existing_with_value(self, space):
        w_res = space.execute("return {}.fetch('a', 1)")
        assert self.unwrap(space, w_res) == 1

    def test_fetch_non_existing_with_block(self, space):
        w_res = space.execute("return {}.fetch('a') { 1 }")
        assert self.unwrap(space, w_res) == 1

    def test_fetch_non_existing_with_no_value_and_no_block(self, space):
        with self.raises(space, "KeyError"):
            space.execute("return {}.fetch('a')")

    def test_fetch_no_args(self, space):
        with self.raises(space, "ArgumentError"):
            space.execute("{}.fetch()")

    def test_delete(self, space):
        w_res = space.execute("""
        x = {2 => 3, 4 => 5}
        return [x.delete(2), x.keys, x.delete(123)]
        """)
        assert self.unwrap(space, w_res) == [3, [4], None]

    def test_delete_with_block(self, space):
        w_res = space.execute("return {}.delete(3) { |a| a }")
        assert space.int_w(w_res) == 3

    def test_replace(self, space):
        w_res = space.execute("return {}.replace({'a' => 1}).keys")
        assert self.unwrap(space, w_res) == ['a']

    def test_keys(self, space):
        w_res = space.execute("""
        x = {2 => 3, "four" => 5, 1 => 3, '1' => 'a'}
        return x.keys
        """)
        assert self.unwrap(space, w_res) == [2, "four", 1, "1"]

    def test_values(self, space):
        w_res = space.execute("""
        x = {2 => 3, "four" => 5, 1 => 3, '1' => 'a'}
        return x.values
        """)
        assert self.unwrap(space, w_res) == [3, 5, 3, "a"]

    def test_each_key(self, space):
        w_res = space.execute("""
        x = {2 => 3, "four" => 5, 3 => 2}
        result = []
        x.each_key do |k|
          result << k
        end
        return result
        """)
        assert self.unwrap(space, w_res) == [2, "four", 3]

    def test_each_with_object(self, space):
        w_res = space.execute("""
        h = {a: 1, b: 2}
        r = h.each_with_object([]) { |(k, v), m| m << k << v }
        return [r, h.each_with_object(0).class.name]
        """)
        assert self.unwrap(space, w_res) == [["a", 1, "b", 2], "Enumerator"]

    def test_each(self, space):
        w_res = space.execute("""
        x = {2 => 3, "four" => 5, 3 => 2}
        result = []
        x.each do |k, v|
          result << [k, v]
        end
        return result
        """)
        assert self.unwrap(space, w_res) == [[2, 3], ["four", 5], [3, 2]]
        w_res = space.execute("""
        result = []
        {2 => 3}.each_pair do |k, v|
          result << [k, v]
        end
        return result
        """)
        assert self.unwrap(space, w_res) == [[2, 3]]

    def test_includep(self, space):
        w_res = space.execute("""
        h = { "a" => 100, "b" => 200 }
        return h.include?("a"), h.include?("z"), h.key?("a"), h.key?("z"), h.has_key?("a"), h.has_key?("z"), h.member?("a"), h.member?("z")
        """)
        assert self.unwrap(space, w_res) == [True, False, True, False, True, False, True, False]

    def test_size(self, space):
        w_res = space.execute("return {}.size")
        assert space.int_w(w_res) == 0
        w_res = space.execute("return {:a => 2}.size")
        assert space.int_w(w_res) == 1

    def test_emptyp(self, space):
        w_res = space.execute("return {}.empty?")
        assert w_res is space.w_true
        w_res = space.execute("return {1 => 2}.empty?")
        assert w_res is space.w_false

    def test_equal(self, space):
        w_res = space.execute("return {} == nil")
        assert w_res is space.w_false
        w_res = space.execute("return {1 => 2, 2 => 3} == {2 => 3, 1 => 2}")
        assert w_res is space.w_true
        w_res = space.execute("return {} == {}")
        assert w_res is space.w_true
        w_res = space.execute("return {} == {1 => 2}")
        assert w_res is space.w_false
        w_res = space.execute("""
        h = {}
        return h == h
        """)
        assert w_res is space.w_true

    def test_shift(self, space):
        w_res = space.execute("return {}.shift")
        assert w_res is space.w_nil
        w_res = space.execute("return {3 => 4}.shift")
        assert self.unwrap(space, w_res) == [3, 4]

    def test_dup(self, space):
        w_res = space.execute("return {2 => 4}.dup.length")
        assert space.int_w(w_res) == 1

    def test_hash(self, space):
        w_res = space.execute("""
        a = {1 => 2, :x => "y"}
        b = {:x => "y", 1 => 2}
        return [a.hash == b.hash, a.hash == {1 => 2}.hash, {}.hash == {}.hash,
                {1 => 2}.hash == {2 => 1}.hash, a.hash.class.name]
        """)
        assert self.unwrap(space, w_res) == [True, False, True, False, "Integer"]

    def test_transform_keys(self, space):
        w_res = space.execute("""
        h = {"a" => 1, "b" => 2}
        r = []
        r << h.transform_keys(&:to_sym)
        r << h.transform_keys("a" => :x)
        r << h.transform_keys("a" => :x) { |k| k.upcase }
        r << h.transform_keys.class.name
        r << h.transform_keys { |k| "k" }
        r << h
        return r
        """)
        assert self.unwrap(space, w_res) == [
            {"a": 1, "b": 2}, {"x": 1, "b": 2}, {"x": 1, "B": 2},
            "Enumerator", {"k": 2}, {"a": 1, "b": 2},
        ]
        with self.raises(space, "TypeError"):
            space.execute("{}.transform_keys(1)")

    def test_reject_bang_and_select_bang(self, space):
        w_res = space.execute("""
        r = []
        r << {a: 1, b: 2}.reject! { |k, v| v == 1 } << {a: 1}.reject! { false }
        r << {a: 1}.select! { true } << {a: 1}.select! { false } << {a: 1}.filter! { false }
        r << {a: 1}.delete_if { false } << {a: 1}.keep_if { false }
        h = {a: 1, b: 2}
        r << h.reject! { |k, v| h.size == 2 } << h
        seen = []
        {a: 1}.reject! { |x| seen << x; false }
        {a: 1}.reject! { |*x| seen << x; false }
        r << seen
        r << {a: 1}.freeze.reject!.class.name << {a: 1}.freeze.delete_if.class.name
        return r
        """)
        assert self.unwrap(space, w_res) == [
            {"b": 2}, None, None, {}, {}, {"a": 1}, {}, {"b": 2}, {"b": 2},
            ["a", ["a", 1]], "Enumerator", "Enumerator",
        ]
        with self.raises(space, "FrozenError"):
            space.execute("{a: 1}.freeze.reject! { true }")
        with self.raises(space, "FrozenError"):
            space.execute("{a: 1}.freeze.keep_if { true }")

    def test_filter_storage_transition(self, space):
        w_res = space.execute('''
        result = []
        [:reject!, :delete_if, :select!, :keep_if].each do |method|
          h = {a: 1, b: 2, c: 3}
          seen = []
          h.send(method) do |key, value|
            seen << [key, value]
            if key == :a
              h[Object.new]
              h[:b] = 20
              h.delete(:c)
            end
            method == :select! || method == :keep_if
          end
          result << seen << h
        end
        return result
        ''')
        assert self.unwrap(space, w_res) == [
            [['a', 1], ['b', 20]], {'a': 1, 'b': 20}] * 4

    def test_iteration_observes_deletions_and_updates(self, space):
        w_res = space.execute('''
        results = []
        [{a: 1, b: 2, c: 3}, {a: 1, b: 2, c: 3}.compare_by_identity,
         {1 => 1, 2 => 2, 3 => 3}].each do |h|
          keys = h.keys
          seen = []
          h.each do |key, value|
            seen << value
            if key == keys[0]
              h.delete(keys[0])
              h[keys[1]] = 20
              h.delete(keys[2])
            end
          end
          results << seen
        end
        return results
        ''')
        assert self.unwrap(space, w_res) == [[1, 20]] * 3

    def test_symbol_storage(self, space):
        from topaz.objects.hashobject import SymbolDictStrategy, ObjectDictStrategy
        w_hash = space.execute('return {a: 1, b: 2}')
        assert w_hash.strategy is space.fromcache(SymbolDictStrategy)
        assert self.unwrap(space, w_hash.getitem(space.newsymbol('a'))) == 1
        assert not w_hash.contains(space.newsymbol('missing'))
        w_hash.setitem(space.newsymbol('a'), space.newint(3))
        assert self.unwrap(space, space.send(w_hash, 'keys')) == ['a', 'b']
        assert w_hash.strategy is space.fromcache(SymbolDictStrategy)
        w_hash.setitem(space.newint(42), space.newint(4))
        assert w_hash.strategy is space.fromcache(ObjectDictStrategy)
        assert self.unwrap(space, space.send(w_hash, 'keys')) == ['a', 'b', 42]
        assert self.unwrap(space, space.send(w_hash, 'values')) == [3, 2, 4]

    def test_symbol_custom_key_fallback(self, space):
        w_res = space.execute('''
        class SymbolAlias
          def hash; :a.hash; end
          def eql?(other); other == :a; end
        end
        key = SymbolAlias.new
        result = []
        result << {a: 7}[key]
        result << {a: 7}.key?(key)
        result << {a: 7}.delete(key)
        h = {a: 7, b: 8}
        h[key] = 9
        result << h.keys << h.values
        result << {a: 7}.merge({key => 2}) { |k, old, new| old + new }.values
        result << {key => 7}.transform_keys({a: :renamed}).keys
        return result
        ''')
        assert self.unwrap(space, w_res) == [7, True, 7, ['a', 'b'], [9, 8], [9], ['renamed']]

    def test_symbol_storage_copy_and_identity(self, space):
        from topaz.objects.hashobject import SymbolDictStrategy, IdentityDictStrategy
        w_hash = space.execute('return {a: 1, b: 2}.dup.rehash')
        assert w_hash.strategy is space.fromcache(SymbolDictStrategy)
        assert space.send(w_hash, 'compare_by_identity?') is space.w_false
        w_copy = w_hash.copy_keywords(space)
        w_copy.delete(space.newsymbol('a'))
        assert w_hash.size() == 2
        assert w_copy.size() == 1
        space.send(w_hash, 'compare_by_identity')
        assert w_hash.strategy is space.fromcache(IdentityDictStrategy)
        assert self.unwrap(space, space.send(w_hash, 'keys')) == ['a', 'b']

    def test_symbol_storage_transition_during_iteration(self, space):
        w_res = space.execute('''
        h = {a: 1, b: 2, c: 3}
        seen = []
        h.each do |key, value|
          seen << [key, value]
          if key == :a
            h[Object.new] # read-only operation switches storage
            h[:b] = 20
            h.delete(:c)
          end
        end
        h = {a: 1, b: 2}
        iter = Topaz::HashIterator.new(h)
        first = iter.next
        h[Object.new]
        h[:b] = 20
        return [seen, first, iter.next]
        ''')
        assert self.unwrap(space, w_res) == [[['a', 1], ['b', 20]], ['a', 1], ['b', 20]]

    def test_symbol_storage_frozen_lookup_and_identity_custom_key(self, space):
        w_res = space.execute('''
        class SymbolAlias
          def hash; :a.hash; end
          def eql?(other); other == :a; end
        end
        key = SymbolAlias.new
        h = {a: 7}.freeze
        result = [h[key], h.key?(key), h.frozen?]
        h = {a: 7}.compare_by_identity
        result << h[key] << h.key?(key)
        h[key] = 8
        result << h[:a] << h[key] << h.size << h.compare_by_identity?
        return result
        ''')
        assert self.unwrap(space, w_res) == [7, True, True, None, False, 7, 8, 2, True]
