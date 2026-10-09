from rpython.rlib.rbigint import rbigint

from ..base import BaseTopazTest
import pytest


class TestStringObject(BaseTopazTest):
    def test_new(self, space):
        w_res = space.execute("return String.new('abc')")
        assert space.str_w(w_res) == "abc"
        w_res = space.execute("return String.new")
        assert space.str_w(w_res) == ""
        w_res = space.execute("""
        class StrSub < String; end
        s = "orig"
        s.send(:initialize, "new")
        u = "x"
        u.send(:initialize, encoding: "BINARY")
        rebound = "b".b
        rebound.send(:initialize, "utf")
        return [String.new.encoding.to_s, String.new("ab").encoding.to_s, String.new("ab".b).encoding.to_s,
                String.new(encoding: "UTF-8").encoding.to_s, String.new("x", encoding: "ASCII-8BIT").encoding.to_s,
                String.new(capacity: 100), String.new("q", capacity: 5), StrSub.new("z").class.name,
                StrSub.new.class.name, s, u, u.encoding.to_s, rebound.encoding.to_s, String.new("ab").frozen?]
        """)
        assert self.unwrap(space, w_res) == [
            "ASCII-8BIT", "UTF-8", "ASCII-8BIT", "UTF-8", "ASCII-8BIT", "", "q", "StrSub", "StrSub",
            "new", "x", "ASCII-8BIT", "UTF-8", False]
        with self.raises(space, "TypeError"):
            space.execute("String.new(nil)")
        with self.raises(space, "TypeError"):
            space.execute("String.new(1)")
        with self.raises(space, "ArgumentError", "wrong number of arguments (given 2, expected 0..1)"):
            space.execute("String.new('a', 'b')")
        with self.raises(space, "ArgumentError", "unknown keyword: :foo"):
            space.execute("String.new(foo: 1)")
        with self.raises(space, "TypeError"):
            space.execute("String.new({encoding: 'UTF-8'})")
        with self.raises(space, "FrozenError"):
            space.execute("'a'.freeze.send(:initialize, 'b')")

    def test_escape_html(self, space):
        w_res = space.execute("""
        plain = "nothing to do"
        return [plain.__topaz_escape_html.equal?(plain), "".__topaz_escape_html,
                %q{<a href="x">Tom & Jerry's</a>}.__topaz_escape_html,
                "&amp;".__topaz_escape_html, "\\xff<".b.__topaz_escape_html.bytesize]
        """)
        assert self.unwrap(space, w_res) == [
            True, "", "&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;",
            "&amp;amp;", 5]

    def test_lshift(self, space):
        w_res = space.execute('return "abc" << "def" << "ghi"')
        assert space.str_w(w_res) == "abcdefghi"
        w_res = space.execute('return "abc".concat("def").concat("ghi")')
        assert space.str_w(w_res) == "abcdefghi"

    def test_plus(self, space):
        w_res = space.execute('return "abc" + "def" + "ghi"')
        assert space.str_w(w_res) == "abcdefghi"

    def test_append_single_bytes(self, space):
        from topaz.objects.stringobject import ConstantStringStrategy
        w_out = space.newstr_fromstr('prefix')
        for byte in range(256):
            w_byte = space.newstr_fromstr(chr(byte))
            assert w_byte.strategy is space.fromcache(ConstantStringStrategy)
            w_out.extend(space, w_byte)
            assert space.str_w(w_byte) == chr(byte)
        assert space.str_w(w_out) == 'prefix' + ''.join(chr(i) for i in range(256))

    def test_append_aliasing_and_encoding(self, space):
        w_res = space.execute('''
        s = 'a'
        s << s
        s << '' << 'bc'
        s << s
        binary = "\\xff".b
        byte = "\\x00".b
        binary << byte
        return [s, binary.bytes, byte.bytes, binary.encoding.name]
        ''')
        assert self.unwrap(space, w_res) == ['aabcaabc', [255, 0], [0], 'ASCII-8BIT']

    def test_mul(self, space):
        w_res = space.execute("return 'abc' * 2")
        assert space.str_w(w_res) == "abcabc"
        w_res = space.execute("return ('abc' << 'def') * 3")
        assert space.str_w(w_res) == "abcdefabcdefabcdef"

    def test_to_s(self, space):
        w_res = space.execute('return "ABC".to_s')
        assert space.str_w(w_res) == "ABC"

    def test_inspect(self, space):
        w_res = space.execute('return "abc".inspect')
        assert space.str_w(w_res) == '"abc"'

    def test_to_str(self, space):
        w_res = space.execute('return "ABC".to_str')
        assert space.str_w(w_res) == "ABC"

    def test_ord(self, space):
        w_res = space.execute('return "a".ord')
        assert space.int_w(w_res) == 97
        w_res = space.execute('return "asd".ord')
        assert space.int_w(w_res) == 97
        with self.raises(space, "ArgumentError", "empty string"):
            space.execute("''.ord")

    def test_length(self, space):
        w_res = space.execute("return 'ABC'.length")
        assert space.int_w(w_res) == 3
        w_res = space.execute("return 'ABC'.size")
        assert space.int_w(w_res) == 3

    def test_unpack_utf8(self, space):
        w_res = space.execute("""
        def t; yield; rescue ArgumentError => e; e.message; end
        return [
          "\\xc3\\xa9".unpack("U"), "a\\xc3\\xa9\\xe2\\x82\\xac\\xf0\\x9d\\x84\\x9e".unpack("U*"),
          "a\\xc3\\xa9".unpack("U"), "".unpack("U"), "".unpack1("U"), "\\xc3\\xa9".unpack1("U"),
          "ab".unpack("U*", offset: 1), t { "\\xff".unpack("U") },
          t { "\\xc3".unpack("U") }, t { "\\xc0\\x80".unpack("U") },
          t { "\\xc3a".unpack("U") }, "\\xed\\xa0\\x80".unpack("U"),
        ]
        """)
        assert self.unwrap(space, w_res) == [
            [233], [97, 233, 8364, 119070],
            [97], [], None, 233,
            [98], "malformed UTF-8 character",
            "malformed UTF-8 character (expected 2 bytes, given 1 bytes)",
            "redundant UTF-8 sequence",
            "malformed UTF-8 character", [55296],
        ]

    def test_emptyp(self, space):
        w_res = space.execute("return ''.empty?")
        assert w_res is space.w_true
        w_res = space.execute("return 'a'.empty?")
        assert w_res is space.w_false

    def test_subscript_constant(self, space):
        w_res = space.execute("""
        a = "hello there"
        return [
          a[1],
          a[2, 3],
          a[2..3],
          a[-3, 2],
          a[7..-2],
          a[-4..-2],
          a[-2..-4],
          a[12..-1],
        ]
        """)
        assert self.unwrap(space, w_res) == ["e", "llo", "ll", "er", "her", "her", "", None]

    def test_subscript_mutable(self, space):
        w_res = space.execute("""
        a = "hello" << " " << "there"
        return [
          a[1],
          a[2, 3],
          a[2..3],
          a[-3, 2],
          a[7..-2],
          a[-4..-2],
          a[-2..-4],
          a[12..-1],
        ]
        """)
        assert self.unwrap(space, w_res) == ["e", "llo", "ll", "er", "her", "her", "", None]

    def test_comparator_lt(self, space):
        w_res = space.execute("return 'a' <=> 'b'")
        assert space.int_w(w_res) == -1

    def test_comparator_eq(self, space):
        w_res = space.execute("return 'a' <=> 'a'")
        assert space.int_w(w_res) == 0

    def test_comparator_gt(self, space):
        w_res = space.execute("return 'b' <=> 'a'")
        assert space.int_w(w_res) == 1

    def test_comparator_to_type_without_to_str(self, space):
        w_res = space.execute("return 'b' <=> 1")
        assert w_res is space.w_nil

    def test_comparator_to_type_with_to_str(self, space):
        w_res = space.execute("""
        class A
          def to_str; 'A'; end
          def <=>(other); other <=> self.to_str; end
        end
        return 'A' <=> A.new
        """)
        assert space.int_w(w_res) == 0

    def test_eqlp(self, space):
        w_res = space.execute("return 'abc'.eql? 2")
        assert w_res is space.w_false
        w_res = space.execute("return 'abc'.eql? 'abc'")
        assert w_res is space.w_true

    def test_b(self, space):
        w_res = space.execute("""
        class MyStr < String; end
        s = "ab\\xc3\\xa9"
        s.instance_variable_set(:@x, 1)
        b = s.b
        b << "z"
        return [b, b.encoding.to_s, s.encoding.to_s, s, b.class.name, MyStr.new("q").b.class.name,
                b.instance_variable_get(:@x), b.frozen?, "x".freeze.b.frozen?]
        """)
        assert self.unwrap(space, w_res) == [
            "ab\xc3\xa9z", "ASCII-8BIT", "UTF-8", "ab\xc3\xa9", "String", "String",
            None, False, False]

    def test_hash(self, space):
        w_res = space.execute("""
        return ['abc'.hash, ('a' << 'b' << 'c').hash]
        """)
        h1, h2 = self.unwrap(space, w_res)
        assert h1 == h2

    def test_to_sym(self, space):
        w_res = space.execute("return 'abc'.to_sym")
        assert space.symbol_w(w_res) == "abc"

    def test_clear(self, space):
        w_res = space.execute("""
        a = 'hi'
        b = a
        a.clear
        return [a, b]
        """)
        assert self.unwrap(space, w_res) == ["", ""]

        w_res = space.execute("return ('a' << 'b').clear")
        assert self.unwrap(space, w_res) == ""

    @pytest.mark.parametrize('method', ['ljust', 'rjust'])
    def test_justify_boundaries(self, space, method):
        w_res = space.execute('''
        s = 'abc'
        pad = 'xy'
        first = s.%s(8, pad)
        pad.replace('z')
        return [first, s.%s(5, pad), s.%s(-1), s.%s(3).equal?(s)]
        ''' % ((method,) * 4))
        expected = ['abcxyxyx', 'abczz'] if method == 'ljust' else [
            'xyxyxabc', 'zzabc']
        assert self.unwrap(space, w_res) == expected + ['abc', False]
        with self.raises(space, 'ArgumentError', 'zero width padding'):
            space.execute("'abc'.%s(0, '')" % method)

    def test_ljust(self, space):
        w_res = space.execute("""
        a = 'hi'
        return a, a.ljust(1)
        """)
        w_original, w_adjusted = space.listview(w_res)
        assert w_original is not w_adjusted
        assert space.str_w(w_adjusted) == space.str_w(w_original)

        w_res = space.execute("return 'a'.ljust(3)")
        assert space.str_w(w_res) == "a  "

        w_res = space.execute("return 'a'.ljust(3, 'l')")
        assert space.str_w(w_res) == "all"

        w_res = space.execute("return 'a'.ljust(5, '-_*')")
        assert space.str_w(w_res) == "a-_*-"

        with self.raises(space, "ArgumentError", "zero width padding"):
            space.execute("'hi'.ljust(10, '')")

    def test_index(self, space):
        w_res = space.execute("return 'abc'.index 'a'")
        assert space.int_w(w_res) == 0
        w_res = space.execute("return 'abc'.index 'bc'")
        assert space.int_w(w_res) == 1
        w_res = space.execute("return 'aba'.index 'a', 1")
        assert space.int_w(w_res) == 2
        w_res = space.execute("return 'aba'.index 'c', 1")
        assert w_res is space.w_nil
        w_res = space.execute("return 'aba'.index /ba/")
        assert space.int_w(w_res) == 1
        w_res = space.execute("return 'aba'.index /xyz/")
        assert w_res is space.w_nil
        with self.raises(space, "TypeError", "no implicit conversion of Integer into String"):
            space.execute("'a b c'.index 12")

    def test_rindex(self, space):
        w_res = space.execute('"hello".rindex("e")')
        assert space.int_w(w_res) == 1
        w_res = space.execute('"hello".rindex("l")')
        assert space.int_w(w_res) == 3
        w_res = space.execute('"hello".rindex("l", -3)')
        assert space.int_w(w_res) == 2
        w_res = space.execute('"hello".rindex("h", -5)')
        assert space.int_w(w_res) == 0
        w_res = space.execute('"hello".rindex(/[aeiou]/, -2)')
        assert space.int_w(w_res) == 1
        w_res = space.execute('"hello".rindex(/[aeiou]/, 0)')
        assert w_res is space.w_nil
        w_res = space.execute('"hello".rindex(/[aeiou]/, 10)')
        assert space.int_w(w_res) == 4
        w_res = space.execute('"hello".rindex(/[aeiou]/, -1)')
        assert space.int_w(w_res) == 4
        w_res = space.execute('"hello".rindex(/[aeiou]/, -10)')
        assert w_res is space.w_nil
        w_res = space.execute('"hello".rindex(/[x]/)')
        assert w_res is space.w_nil
        w_res = space.execute('"hello".rindex("x")')
        assert w_res is space.w_nil
        with self.raises(space, "TypeError", "no implicit conversion of Integer into String"):
            space.execute('"hello".rindex(123)')

    def test_split(self, space):
        w_res = space.execute("return 'a b c'.split")
        assert self.unwrap(space, w_res) == ["a", "b", "c"]
        w_res = space.execute("return 'a-b-c'.split('-')")
        assert self.unwrap(space, w_res) == ["a", "b", "c"]
        w_res = space.execute("return 'a-b-c'.split('-', 2)")
        assert self.unwrap(space, w_res) == ["a", "b-c"]
        w_res = space.execute("return 'a b c'.split(' ', -1)")
        assert self.unwrap(space, w_res) == ["a", "b", "c"]
        with self.raises(space, "TypeError", "wrong argument type Integer (expected Regexp)"):
            space.execute("'a b c'.split(12)")

    def test_split_regexp(self, space):
        w_res = space.execute("return \"now's  the time\".split(/ /)")
        assert self.unwrap(space, w_res) == ["now's", "", "the", "time"]
        w_res = space.execute('return "1, 2.34,56, 7".split(%r{,\s*})')
        assert self.unwrap(space, w_res) == ["1", "2.34", "56", "7"]
        w_res = space.execute('return "1, 2.34,56, 7".split(%r{,\s*}, 0)')
        assert self.unwrap(space, w_res) == ["1", "2.34", "56", "7"]
        w_res = space.execute('return "1, 2.34,56, 7".split(%r{,\s*}, -1)')
        assert self.unwrap(space, w_res) == ["1", "2.34", "56", "7"]
        w_res = space.execute('return "1, 2.34,56, 7,".split(%r{,\s*}, -2)')
        assert self.unwrap(space, w_res) == ["1", "2.34", "56", "7", ""]
        w_res = space.execute('return "1, 2.34,56, 7".split(%r{,\s*}, 4)')
        assert self.unwrap(space, w_res) == ["1", "2.34", "56", "7"]
        w_res = space.execute('return "1, 2.34,56, 7".split(%r{,\s*}, 3)')
        assert self.unwrap(space, w_res) == ["1", "2.34", "56, 7"]
        w_res = space.execute('return "1, 2.34,56, 7,".split(%r{,\s*}, 6)')
        assert self.unwrap(space, w_res) == ["1", "2.34", "56", "7", ""]
        w_res = space.execute('return "hello".split(//)')
        assert self.unwrap(space, w_res) == ["h", "e", "l", "l", "o"]
        w_res = space.execute('return "hello".split(//, 3)')
        assert self.unwrap(space, w_res) == ["h", "e", "llo"]
        w_res = space.execute('return "hello".split(/((.)(.))/, 3)')
        assert self.unwrap(space, w_res) == ["", "he", "h", "e", "", "ll", "l", "l", "o"]

    def test_dup(self, space):
        w_res = space.execute("""
        x = "abc"
        y = x.dup
        x << "def"
        return [x, y]
        """)
        x, y = self.unwrap(space, w_res)
        assert x == "abcdef"
        assert y == "abc"

    def test_dup_mutable(self, space):
        w_res = space.execute("return ('abc' << 'def').dup")
        assert self.unwrap(space, w_res) == 'abcdef'

    def test_to_i(self, space):
        w_res = space.execute('return "1234".to_i')
        assert space.int_w(w_res) == 1234
        w_res = space.execute('return "1010".to_i(2)')
        assert space.int_w(w_res) == 10
        w_res = space.execute('return "77".to_i(8)')
        assert space.int_w(w_res) == 63
        w_res = space.execute('return "AA".to_i(16)')
        assert space.int_w(w_res) == 170
        w_res = space.execute('return "12a".to_i')
        assert space.int_w(w_res) == 12
        w_res = space.execute('return "-a".to_i')
        assert space.int_w(w_res) == 0
        w_res = space.execute('return "".to_i')
        assert space.int_w(w_res) == 0
        w_res = space.execute('return "-12fdsa".to_i')
        assert space.int_w(w_res) == -12
        w_res = space.execute("return '1_2_3'.to_i")
        assert space.int_w(w_res) == 123
        w_res = space.execute("return '_1_2_3'.to_i")
        assert space.int_w(w_res) == 0
        w_res = space.execute("return '   123'.to_i")
        assert space.int_w(w_res) == 123

        w_res = space.execute("return '234124123123123121231231'.to_i")
        assert space.bigint_w(w_res) == rbigint.fromlong(234124123123123121231231)

        with self.raises(space, "ArgumentError"):
            space.execute('"".to_i(1)')
        with self.raises(space, "ArgumentError"):
            space.execute('"".to_i(37)')

    def test_to_f(self, space):
        w_res = space.execute('return "123.45".to_f')
        assert space.float_w(w_res) == 123.45

        w_res = space.execute('return "45.67 degrees".to_f')
        assert space.float_w(w_res) == 45.67

        w_res = space.execute('return "thx1138".to_f')
        assert space.float_w(w_res) == 0.0

        w_res = space.execute('return "123.45e1".to_f')
        assert space.float_w(w_res) == 1234.5

        w_res = space.execute('return "  123.45e1".to_f')
        assert space.float_w(w_res) == 1234.5

    def test_swapcase(self, space):
        w_res = space.execute("""
        a = "AbC123aBc"
        a.swapcase!
        return a
        """)
        assert self.unwrap(space, w_res) == "aBc123AbC"

        w_res = space.execute("return 'AbC123aBc'.swapcase")
        assert self.unwrap(space, w_res) == "aBc123AbC"

        w_res = space.execute("return '123'.swapcase!")
        assert w_res is space.w_nil

    def test_upcase(self, space):
        w_res = space.execute("""
        a = "AbC123aBc"
        a.upcase!
        return a
        """)
        assert self.unwrap(space, w_res) == "ABC123ABC"

        w_res = space.execute("return 'AbC123aBc'.upcase")
        assert self.unwrap(space, w_res) == "ABC123ABC"

        w_res = space.execute("return '123'.upcase!")
        assert w_res is space.w_nil

    def test_downcase(self, space):
        w_res = space.execute("""
        a = "AbC123aBc"
        a.downcase!
        return a
        """)
        assert self.unwrap(space, w_res) == "abc123abc"

        w_res = space.execute("return 'AbC123aBc'.downcase")
        assert self.unwrap(space, w_res) == "abc123abc"

        w_res = space.execute("return '123'.downcase!")
        assert w_res is space.w_nil

    def test_capitalize(self, space):
        w_res = space.execute("""
        a = "123ABC"
        a.capitalize!
        return a
        """)
        assert self.unwrap(space, w_res) == "123abc"

        w_res = space.execute("return 'hello'.capitalize")
        assert self.unwrap(space, w_res) == "Hello"
        w_res = space.execute("return 'HELLO'.capitalize")
        assert self.unwrap(space, w_res) == "Hello"
        w_res = space.execute("return '123'.capitalize!")
        assert w_res is space.w_nil

    @pytest.mark.parametrize('method', ['tr', 'tr!', 'tr_s', 'tr_s!'])
    @pytest.mark.parametrize('source,replacement', [('z-a', 'x'), ('a', 'z-a')])
    def test_tr_invalid_range(self, space, method, source, replacement):
        w_res = space.execute('''
        s = 'abba'
        begin
          s.%s('%s', '%s')
        rescue ArgumentError => error
          return [s, error.message]
        end
        ''' % (method, source, replacement))
        assert self.unwrap(space, w_res) == [
            'abba', 'invalid range "z-a" in string transliteration']

    def test_tr(self, space):
        w_res = space.execute("return 'hello'.tr('el', 'ip')")
        assert space.str_w(w_res) == "hippo"
        w_res = space.execute("return 'hello'.tr('aeiou', '*')")
        assert space.str_w(w_res) == "h*ll*"
        w_res = space.execute("return 'hello'.tr('a-y', 'b-z')")
        assert space.str_w(w_res) == "ifmmp"
        w_res = space.execute("return 'hello'.tr('^aieou', '*')")
        assert space.str_w(w_res) == "*e**o"
        w_res = space.execute("return 'hello'.tr!('','').nil?")
        assert self.unwrap(space, w_res) is True
        w_res = space.execute("""
        s = 'hello'
        s.tr!('e', 'a')
        return s
        """)
        assert space.str_w(w_res) == "hallo"
        w_res = space.execute("return 'x'.tr('x', '-')")
        assert space.str_w(w_res) == "-"

    def test_squeeze(self, space):
        w_res = space.execute("""
        def t; yield; rescue => e; e.class.name; end
        class S2 < String; end
        s = "a  b"; r = s.squeeze!(" ")
        return [
          "aaa".squeeze, "aa  bb".squeeze(" "), "aabbcc".squeeze("a-b"),
          "aabbcc".squeeze("^a"), "aabb".squeeze("ab", "a"), "ab".squeeze("-"),
          "aa".squeeze(""), "aa".squeeze("^"), "a^^b".squeeze("^"), "a--b".squeeze("\\\\-"),
          "a--b".squeeze!("-"), "ab".squeeze!("-"), t { "ab".freeze.squeeze!("a") },
          t { "aa".squeeze(1) }, t { "aa".squeeze("b-a") },
          S2.new("aab").squeeze.class.name, S2.new("aab").squeeze!.class.name,
          r.equal?(s), s,
        ]
        """)
        assert self.unwrap(space, w_res) == [
            "a", "aa bb", "abcc",
            "aabc", "abb", "ab",
            "aa", "aa", "a^b", "a-b",
            "a-b", None, "FrozenError",
            "TypeError", "ArgumentError",
            "String", "S2",
            True, "a b",
        ]

    def test_tr_s(self, space):
        w_res = space.execute("return 'hello'.tr_s('l', 'r')")
        assert space.str_w(w_res) == "hero"
        w_res = space.execute("return 'hello'.tr_s('el', '*')")
        assert space.str_w(w_res) == "h*o"
        w_res = space.execute("return 'hello'.tr_s('el', 'hx')")
        assert space.str_w(w_res) == "hhxo"
        w_res = space.execute("""
        s = 'hello'
        s.tr_s!('el', 'hx')
        return s
        """)
        assert space.str_w(w_res) == "hhxo"
        w_res = space.execute("return 'hello'.tr_s!('','').nil?")
        assert self.unwrap(space, w_res) is True

    def test_match_operator(self, space):
        w_res = space.execute("return 'abc' =~ 1")
        assert w_res is space.w_nil
        w_res = space.execute("return 'abc' =~ /abc/")
        assert space.int_w(w_res) == 0
        w_res = space.execute("""
        '' =~ /()/
        return $1
        """)
        assert space.str_w(w_res) == ""

    def test_match_method(self, space):
        w_res = space.execute("return 'abc'.match('bc').begin 0")
        assert space.int_w(w_res) == 1

    def test_getbyte(self, space):
        w_res = space.execute("return 'abc'.getbyte 0")
        assert space.int_w(w_res) == 97
        w_res = space.execute("return 'abc'.getbyte 2")
        assert space.int_w(w_res) == 99
        w_res = space.execute("return 'abc'.getbyte 3")
        assert w_res is space.w_nil
        w_res = space.execute("return 'abc'.getbyte -1")
        assert space.int_w(w_res) == 99
        w_res = space.execute("return 'abc'.getbyte -3")
        assert space.int_w(w_res) == 97
        w_res = space.execute("return 'abc'.getbyte -4")
        assert w_res is space.w_nil

    def test_chomp(self, space):
        assert space.str_w(space.execute('return "hello".chomp')) == "hello"
        assert space.str_w(space.execute('return "hello\\n".chomp')) == "hello"
        assert space.str_w(space.execute('return "hello\\r\\n".chomp')) == "hello"
        assert space.str_w(space.execute('return "hello\\n\\r".chomp')) == "hello"
        assert space.str_w(space.execute('return "hello\\r".chomp')) == "hello"
        assert space.str_w(space.execute('return "hello\\r".chomp("")')) == "hello\r"
        assert space.str_w(space.execute('return "hello \\n there".chomp')) == "hello \n there"
        assert space.str_w(space.execute('return "hello".chomp("llo")')) == "he"
        w_res = space.execute('return "hello".chomp!')
        assert w_res is space.w_nil
        w_res = space.execute('return "".chomp!')
        assert w_res is space.w_nil
        w_res = space.execute('return "abc".chomp!(nil)')
        assert w_res is space.w_nil
        w_res = space.execute('return "abc\\r".chomp!("")')
        assert w_res is space.w_nil

    def test_chop(self, space):
        assert space.str_w(space.execute('return "string\\r\\n".chop')) == "string"
        assert space.str_w(space.execute('return "string\\n\\r".chop')) == "string\n"
        assert space.str_w(space.execute('return "string\\n".chop')) == "string"
        assert space.str_w(space.execute('return "string".chop')) == "strin"
        assert space.str_w(space.execute('return "x".chop.chop')) == ""
        assert space.str_w(space.execute('return "string".chop!')) == "strin"
        w_res = space.execute("return ''.chop!")
        assert w_res is space.w_nil

    def test_reverse(self, space):
        assert space.str_w(space.execute('return "stressed".reverse')) == "desserts"
        w_res = space.execute("""
        a = "stressed"
        a.reverse!
        return a, a.reverse
        """)
        assert self.unwrap(space, w_res) == ["desserts", "stressed"]

    def test_includep(self, space):
        assert space.execute("return 'abc'.include? 'ab'") is space.w_true
        assert space.execute("return 'abc'.include? 'bc'") is space.w_true
        assert space.execute("return 'abc'.include? 'cd'") is space.w_false

    def test_gsub(self, space):
        w_res = space.execute("""
        return 'hello hello'.gsub("he", "ha")
        """)
        assert space.str_w(w_res) == "hallo hallo"
        w_res = space.execute("""
        return 'hello'.gsub(/(.)/, "ha")
        """)
        assert space.str_w(w_res) == "hahahahaha"
        w_res = space.execute("""
        return 'hello'.gsub(/(.)/, "ha\\\\1ho")
        """)
        assert space.str_w(w_res) == "hahhohaehohalhohalhohaoho"
        w_res = space.execute("""
        return 'hello'.gsub(/(.)/) { |e| e + "1" }
        """)
        assert space.str_w(w_res) == "h1e1l1l1o1"
        w_res = space.execute("""
        return 'hello'.gsub('e') { |e| e + "1" }
        """)
        assert space.str_w(w_res) == "he1llo"
        w_res = space.execute("""
        return 'hello'.gsub(/[eo]/, 'e' => 3, 'o' => '*')
        """)
        assert space.str_w(w_res) == "h3ll*"
        w_res = space.execute("""
        return 'hello'.gsub("e", 'e' => 3, 'o' => '*')
        """)
        assert space.str_w(w_res) == "h3llo"
        w_res = space.execute("""
        replacements = [1, 2]
        return 'helloo'.gsub("l", Hash.new { |h, k| replacements.pop() })
        """)
        assert space.str_w(w_res) == "he21oo"

    def test_sub(self, space):
        w_res = space.execute("""
        return 'hello hello'.sub("he", "ha")
        """)
        assert space.str_w(w_res) == "hallo hello"
        w_res = space.execute("""
        return 'hello'.sub(/(.)/, "ha")
        """)
        assert space.str_w(w_res) == "haello"
        w_res = space.execute("""
        return 'hello'.sub(/(.)/, "ha\\\\1ho")
        """)
        assert space.str_w(w_res) == "hahhoello"
        w_res = space.execute("""
        return 'hello'.sub(/(.)/) { |e| e + "1" }
        """)
        assert space.str_w(w_res) == "h1ello"
        w_res = space.execute("""
        return 'hello'.sub('l') { |e| e + "1" }
        """)
        assert space.str_w(w_res) == "hel1lo"
        w_res = space.execute("""
        return 'hello'.sub(/[eo]/, 'e' => 3, 'o' => '*')
        """)
        assert space.str_w(w_res) == "h3llo"
        w_res = space.execute("""
        return 'hello'.sub("e", 'e' => 3, 'o' => '*')
        """)
        assert space.str_w(w_res) == "h3llo"
        w_res = space.execute("""
        replacements = [1, 2]
        return 'helloo'.sub("l", Hash.new { |h, k| replacements.pop() })
        """)
        assert space.str_w(w_res) == "he2loo"
        with self.raises(space, "ArgumentError"):
            space.execute("'string'.sub(/regex/)")

    def test_succ(self, space):
        w_res = space.execute('return "abcd".succ')
        assert space.str_w(w_res) == "abce"
        w_res = space.execute('return "THX1138".succ')
        assert space.str_w(w_res) == "THX1139"
        w_res = space.execute('return "<<koala>>".succ')
        assert space.str_w(w_res) == "<<koalb>>"
        w_res = space.execute('return "ZZZ9999".succ')
        assert space.str_w(w_res) == "AAAA0000"
        w_res = space.execute('return "***".succ')
        assert space.str_w(w_res) == "**+"

    def test_slice(self, space):
        w_res = space.execute('return "this is a string".slice(2)')
        assert space.str_w(w_res) == "i"
        w_res = space.execute('return "hello".slice(2, 3)')
        assert space.str_w(w_res) == "llo"

    def test_slice_i(self, space):
        w_res = space.execute('return "this is a string".slice!(2)')
        assert space.str_w(w_res) == "i"
        w_res = space.execute('return "this is a string".slice!(2, 5)')
        assert space.str_w(w_res) == "is is"
        w_res = space.execute("""
        string = "this is a string"
        string.slice!(2)
        string.slice!(3..6)
        return string
        """)
        assert space.str_w(w_res) == "thsa string"

    @pytest.mark.xfail
    def test_byte_representation(self, space):
        w_res = space.execute('return "\x00".length')
        assert space.int_w(w_res) == 1

        w_res = space.execute("return '\x00'.length")
        assert space.int_w(w_res) == 4

        w_res = space.execute('return "\x04\bi\x00".length')
        assert space.int_w(w_res) == 4

        w_res = space.execute("return '\x04\bi\x00'.length")
        assert space.int_w(w_res) == 11


class TestStringMod(object):
    def test_s(self, space):
        w_res = space.execute("return '1 %s 1' % 'abc'")
        assert space.str_w(w_res) == "1 abc 1"

    def test_f(self, space):
        w_res = space.execute("return ' %f ' % 1.23")
        assert space.str_w(w_res) == " 1.230000 "

    def test_f_width(self, space):
        w_res = space.execute("return '%04f' % 1.23")
        assert space.str_w(w_res) == "1.230000"

    def test_d(self, space):
        w_res = space.execute("return ' %d ' % 12")
        assert space.str_w(w_res) == " 12 "

    def test_d_width(self, space):
        w_res = space.execute("return ' %05d' % 12")
        assert space.str_w(w_res) == " 00012"
        w_res = space.execute("return ' %01d' % 12")
        assert space.str_w(w_res) == " 12"

    def test_array_param(self, space):
        w_res = space.execute("return '%d-%s' % [12, 'happy']")
        assert space.str_w(w_res) == "12-happy"
        w_res = space.execute("return '1%02d%02d%02d%04d' % [1, 2, 3, 4]")
        assert space.str_w(w_res) == "10102030004"


class TestStringEncoding(BaseTopazTest):
    def test_encoding_tag(self, space):
        w_res = space.execute("""
        r = []
        s = "abc"
        r << s.encoding.name
        r << s.force_encoding("ASCII-8BIT").equal?(s) << s.encoding.name
        r << s.dup.encoding.name << s.clone.encoding.name << (s * 2).encoding.name
        r << String.new(s).encoding.name << String.new.encoding.name
        r << String.new("x", encoding: "US-ASCII").encoding.name
        t = +"zzz"; t.replace(s); r << t.encoding.name
        r << s.force_encoding(Encoding::UTF_8).encoding.name
        r << "x".b.encoding.name
        r << s.instance_variables
        r << "x".force_encoding(Encoding::US_ASCII).to_s.encoding.name
        r << ("a".b + "b".b).encoding.name << ("a".b + "b").encoding.name
        return r
        """)
        assert self.unwrap(space, w_res) == [
            "UTF-8", True, "ASCII-8BIT", "ASCII-8BIT", "ASCII-8BIT", "ASCII-8BIT",
            "ASCII-8BIT", "ASCII-8BIT", "US-ASCII", "ASCII-8BIT", "UTF-8", "ASCII-8BIT",
            [], "US-ASCII", "ASCII-8BIT", "UTF-8",
        ]
        with self.raises(space, "FrozenError"):
            space.execute('"abc".freeze.force_encoding("ASCII-8BIT")')
        with self.raises(space, "ArgumentError", "unknown encoding name - nope"):
            space.execute('"abc".force_encoding("nope")')

class TestStringAffixes(BaseTopazTest):
    @pytest.mark.parametrize('mutable_receiver', [False, True])
    @pytest.mark.parametrize('mutable_affix', [False, True])
    @pytest.mark.parametrize('method', ['start_with?', 'end_with?'])
    def test_affix_storage(self, space, mutable_receiver, mutable_affix, method):
        def string(value, mutable):
            if mutable:
                return space.newstr_fromchars(list(value))
            return space.newstr_fromstr(value)
        w_string = string('abc\x00abc', mutable_receiver)
        for affix, expected in [('abc', True), ('ab', method == 'start_with?'),
                                ('bc', method == 'end_with?'), ('', True),
                                ('abc\x00abc', True), ('abc\x00abcd', False),
                                ('abd', False), ('\x00abc', method == 'end_with?')]:
            w_affix = string(affix, mutable_affix)
            assert space.send(w_string, method, [w_affix]) is space.newbool(expected)

    @pytest.mark.parametrize('method', ['start_with?', 'end_with?'])
    def test_affix_multiple_and_conversion(self, space, method):
        w_res = space.execute('''
        class Affix
          def initialize(s); @s = s; end
          def to_str; @s; end
        end
        class BadAffix
          def to_str; raise 'must not be called'; end
        end
        s = 'abcabc'
        return [s.%s(), s.%s('x', 'abc'), s.%s('x', 'y'),
                s.%s('', BadAffix.new), s.%s(Affix.new('abc')),
                s.%s(Object.new, Affix.new(nil), 'abc')]
        ''' % ((method,) * 6))
        assert self.unwrap(space, w_res) == [False, True, False, True, True, True]
        with self.raises(space, 'TypeError'):
            space.execute("class BadAffix; def to_str; 12; end; end; 'abc'.%s(BadAffix.new)" % method)
        with self.raises(space, 'RuntimeError'):
            space.execute("class BadAffix; def to_str; raise 'conversion'; end; end; 'abc'.%s(BadAffix.new)" % method)

    @pytest.mark.parametrize('method', ['start_with?', 'end_with?'])
    def test_affix_coercion_mutates_receiver(self, space, method):
        w_res = space.execute('''
        class MutatingAffix
          def initialize(s); @s = s; end
          def to_str; @s.replace('z'); 'z'; end
        end
        s = 'abc'
        return s.%s(MutatingAffix.new(s))
        ''' % method)
        assert w_res is space.w_true

    def test_affix_bytes_and_long_strings(self, space):
        w_res = space.execute('''
        s = "\\xc3\\xa9\\x00\\xff".b
        long = 'a' * 1000
        return [s.start_with?("\\xc3\\xa9".b), s.end_with?("\\x00\\xff".b),
                s.start_with?("\\xff".b), long.start_with?('a' * 999),
                long.end_with?('a' * 999), long.end_with?('a' * 999 + 'b')]
        ''')
        assert self.unwrap(space, w_res) == [True, True, False, True, True, False]


class TestStringAsciiOnly(BaseTopazTest):
    @pytest.mark.parametrize('mutable', [False, True])
    def test_ascii_only_storage(self, space, mutable):
        def make(value):
            if mutable:
                return space.newstr_fromchars(list(value))
            return space.newstr_fromstr(value)
        cases = [('', True), ('\x00\x7fabc', True), ('a' * 1000, True),
                 ('\x80' + 'a' * 1000, False), ('a' * 1000 + '\xff', False),
                 ('\xc3\xa9', False)]
        cases += [('a' + chr(byte) + 'z', byte < 128) for byte in range(256)]
        for value, expected in cases:
            assert space.send(make(value), 'ascii_only?') is space.newbool(expected)

    def test_ascii_only_mutation(self, space):
        w_res = space.execute('''
        s = 'abc'
        result = [s.ascii_only?]
        s.setbyte(1, 128)
        result << s.ascii_only?
        s.setbyte(1, 127)
        result << s.ascii_only?
        s << "\\xff".b
        result << s.ascii_only?
        s.clear
        result << s.ascii_only?
        s.replace("\\xc3\\xa9")
        result << s.ascii_only?
        s.replace('ASCII')
        result << s.ascii_only?
        result << Topaz::EncodingSupport.ascii_only?(s)
        return result
        ''')
        assert self.unwrap(space, w_res) == [True, False, True, False, True, False, True, True]


class TestStringUnpackHex(BaseTopazTest):
    @pytest.mark.parametrize('mutable', [False, True])
    def test_unpack_hex_storage(self, space, mutable):
        value = ''.join(chr(i) for i in range(256))
        if mutable:
            w_str = space.newstr_fromchars(list(value))
        else:
            w_str = space.newstr_fromstr(value)
        for high_first in [False, True]:
            for pos in [0, 1, 255, 256]:
                for digits in [0, 1, 3, 2 * (256 - pos)]:
                    if digits > 2 * (256 - pos):
                        continue
                    pairs = ['%02x' % ord(c) for c in value[pos:]]
                    if not high_first:
                        pairs = [s[::-1] for s in pairs]
                    expected = ''.join(pairs)[:digits]
                    w_result = space.send(w_str, '__topaz_unpack_hex', [
                        space.newint(pos), space.newint(digits),
                        space.newbool(high_first)])
                    assert space.str_w(w_result) == expected

    @pytest.mark.parametrize('mutable', [False, True])
    def test_unpack_hex_formats(self, space, mutable):
        w_res = space.execute('''
        s = "\\x12\\xab\\xff"
        %s
        seen = []
        block_result = s.unpack('H2H2') { |part| seen << part }
        return [s.unpack('H*'), s.unpack('h*'), s.unpack('H3C'),
                s.unpack('H0h0C'), s.unpack('H99'), s.unpack('H'),
                s.unpack('h'), s.unpack('H*H2'), ''.unpack('H*'),
                s.unpack('H3', offset: 1), s.unpack('xH2Xh2'),
                s.unpack1('H3'), s.unpack1('h*', offset: 1),
                block_result, seen]
        ''' % ("s << ''" if mutable else ''))
        assert self.unwrap(space, w_res) == [
            ['12abff'], ['21baff'], ['12a', 255], ['', '', 18],
            ['12abff'], ['1'], ['2'], ['12abff', ''], [''],
            ['abf'], ['ab', 'ba'], '12a', 'baff', None, ['12', 'ab']]

    def test_unpack_hex_mutation(self, space):
        w_res = space.execute('''
        s = "\\x12\\xab"
        first = s.unpack1('H*')
        s.setbyte(0, 255)
        second = s.unpack1('H*')
        s.replace("\\x01")
        third = s.unpack1('h*')
        s.clear
        return [first, second, third, s.unpack1('H*')]
        ''')
        assert self.unwrap(space, w_res) == ['12ab', 'ffab', '10', '']

    def test_unpack_hex_invalid_slice(self, space):
        for pos, digits in [(-1, 0), (2, 0), (0, -1), (0, 3)]:
            with self.raises(space, 'ArgumentError', 'invalid hexadecimal slice'):
                space.send(space.newstr_fromstr('a'), '__topaz_unpack_hex', [
                    space.newint(pos), space.newint(digits), space.w_true])


class TestStringUnpackInteger(BaseTopazTest):
    @pytest.mark.parametrize('mutable', [False, True])
    def test_integer_storage(self, space, mutable):
        for size in [1, 2, 4, 8]:
            bits = size * 8
            for value in [0, 1, (1 << (bits - 1)) - 1,
                          1 << (bits - 1), (1 << bits) - 1,
                          0x123456789abcdef & ((1 << bits) - 1)]:
                for big in [False, True]:
                    data = ''.join(chr((value >> (8 * i)) & 255)
                                   for i in range(size))
                    if big:
                        data = data[::-1]
                    data = 'x' + data + 'z'
                    w_str = (space.newstr_fromchars(list(data)) if mutable
                             else space.newstr_fromstr(data))
                    for signed in [False, True]:
                        w_result = space.send(w_str, '__topaz_unpack_integer', [
                            space.newint(1), space.newint(size),
                            space.newbool(big), space.newbool(signed)])
                        expected = value
                        if signed and value >= 1 << (bits - 1):
                            expected -= 1 << bits
                        assert space.bigint_w(w_result).tolong() == expected

    def test_integer_formats_and_short_input(self, space):
        w_res = space.execute('''
        s = "\\x01\\x02\\x03\\x04\\xff\\xfe"
        seen = []
        result = s.unpack('n2C2') { |v| seen << v }
        return [s.unpack('Nn'), s.unpack('Vv'), s.unpack('n*'),
                s.unpack('C0N'), s.unpack('N2C*'), ''.unpack('N2'),
                s.unpack('S>2'), s.unpack('s<', offset: 4),
                s.unpack1('N'), s.unpack1('N', offset: 4),
                result, seen]
        ''')
        assert self.unwrap(space, w_res) == [
            [16909060, 65534], [67305985, 65279], [258, 772, 65534],
            [16909060], [16909060, None, 255, 254], [None, None],
            [258, 772], [-257], 16909060, None, None, [258, 772, 255, 254]]

    def test_integer_mutation(self, space):
        w_res = space.execute('''
        s = "\\x01\\x02"
        a = s.unpack1('n')
        s.setbyte(1, 255)
        b = s.unpack1('n')
        s.replace("\\xff\\xff")
        c = s.unpack1('s>')
        s.clear
        return [a, b, c, s.unpack1('n')]
        ''')
        assert self.unwrap(space, w_res) == [258, 511, -1, None]

    def test_integer_helper_bounds(self, space):
        w_str = space.newstr_fromstr('a')
        for pos, size, message in [
                (0, 0, 'invalid integer width'), (0, 3, 'invalid integer width'),
                (-1, 1, 'invalid integer offset'), (2, 1, 'invalid integer offset')]:
            with self.raises(space, 'ArgumentError', message):
                space.send(w_str, '__topaz_unpack_integer', [
                    space.newint(pos), space.newint(size), space.w_true, space.w_false])
        assert space.send(w_str, '__topaz_unpack_integer', [
            space.newint(0), space.newint(2), space.w_true, space.w_false]) is space.w_nil


class TestStringBase64Encode(BaseTopazTest):
    @pytest.mark.parametrize('mutable', [False, True])
    def test_base64_storage(self, space, mutable):
        import base64
        value = ''.join(chr(i) for i in range(256))
        w_str = (space.newstr_fromchars(list(value)) if mutable
                 else space.newstr_fromstr(value))
        for pos in [0, 1, 127, 253, 254, 255, 256]:
            for length in [0, 1, 2, 3, 4, 5, 256 - pos]:
                if length > 256 - pos:
                    continue
                w_res = space.send(w_str, '__topaz_base64_encode', [
                    space.newint(pos), space.newint(length)])
                assert space.str_w(w_res) == base64.b64encode(value[pos:pos + length])

    def test_base64_padding_and_wrapping(self, space):
        w_res = space.execute('''
        return [ [''].pack('m0'), ['f'].pack('m0'), ['fo'].pack('m0'),
                 ['foo'].pack('m0'), ['foob'].pack('m0'), ['fooba'].pack('m0'),
                 ['foobar'].pack('m0'), [''].pack('m'), ['f'].pack('m'),
                 ['foobar'].pack('m3'), ['foobar'].pack('m4'),
                 ['foobar'].pack('m*'), ['f', 'oo'].pack('m0m0'),
                 ['f'].pack('m0', buffer: 'prefix:') ]
        ''')
        assert self.unwrap(space, w_res) == [
            '', 'Zg==', 'Zm8=', 'Zm9v', 'Zm9vYg==', 'Zm9vYmE=',
            'Zm9vYmFy', '', 'Zg==\n', 'Zm9v\nYmFy\n', 'Zm9v\nYmFy\n',
            'Zm9vYmFy\n', 'Zg==b28=', 'prefix:Zg==']

    def test_base64_mutation_and_coercion(self, space):
        w_res = space.execute('''
        class Base64Source
          def to_str; 'foo'; end
        end
        s = 'foo'
        a = [s].pack('m0')
        s.setbyte(0, 103)
        b = [s].pack('m0')
        s.replace('f')
        c = [s].pack('m0')
        s.clear
        return [a, b, c, [s].pack('m0'), [Base64Source.new].pack('m0')]
        ''')
        assert self.unwrap(space, w_res) == ['Zm9v', 'Z29v', 'Zg==', '', 'Zm9v']

    def test_base64_invalid_slice(self, space):
        for pos, length in [(-1, 0), (2, 0), (0, -1), (0, 2)]:
            with self.raises(space, 'ArgumentError', 'invalid base64 slice'):
                space.send(space.newstr_fromstr('a'), '__topaz_base64_encode', [
                    space.newint(pos), space.newint(length)])
