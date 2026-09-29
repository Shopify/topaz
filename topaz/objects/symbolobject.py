from topaz.module import ClassDef
from topaz.modules.comparable import Comparable
from topaz.objects.objectobject import W_Object
from topaz.objects.stringobject import inspect_string


OPERATOR_SYMBOLS = {}
for _op in ["+", "-", "*", "/", "%", "**", "==", "===", "!=", "=~", "!~",
            "!", "<=>", "<", "<=", ">", ">=", "<<", ">>", "&", "|", "^", "~",
            "+@", "-@", "[]", "[]=", "`"]:
    OPERATOR_SYMBOLS[_op] = None
del _op

SPECIAL_GLOBALS = "~*$?!@/\\;,.=:<>\"&`'+0"


def _is_ident_start(c):
    return c.isalpha() or c == "_" or ord(c) >= 0x80


def _is_ident_char(c):
    return c.isalnum() or c == "_" or ord(c) >= 0x80


def _identifier_end(s, start):
    """The end of the identifier starting at s[start], or -1."""
    if start >= len(s) or not _is_ident_start(s[start]):
        return -1
    end = start + 1
    while end < len(s) and _is_ident_char(s[end]):
        end += 1
    return end


def is_label_symbol(s):
    """Whether `{s: 1}` is how a Hash with the key :s is inspected (3.4)."""
    end = _identifier_end(s, 0)
    if end == -1:
        return False
    return end == len(s) or (end == len(s) - 1 and s[end] in "?!")


def symbol_needs_quotes(s):
    """Whether :s must be written as :"s"."""
    if s in OPERATOR_SYMBOLS:
        return False
    if not s:
        return True
    start = 0
    if s[0] == "$":
        rest = s[1:]
        if len(rest) == 1 and rest in SPECIAL_GLOBALS:
            return False
        if rest.isdigit():
            return False
        if len(rest) == 2 and rest[0] == "-" and _is_ident_char(rest[1]):
            return False
        start = 1
    elif s.startswith("@@"):
        start = 2
    elif s[0] == "@":
        start = 1
    end = _identifier_end(s, start)
    if end == -1:
        return True
    if end == len(s):
        return False
    return not (start == 0 and end == len(s) - 1 and s[end] in "?!=")


class W_SymbolObject(W_Object):
    _immutable_fields_ = ["symbol"]
    classdef = ClassDef("Symbol", W_Object.classdef)
    classdef.include_module(Comparable)

    def __init__(self, space, symbol):
        W_Object.__init__(self, space)
        self.symbol = symbol

    def __deepcopy__(self, memo):
        obj = super(W_SymbolObject, self).__deepcopy__(memo)
        obj.symbol = self.symbol
        return obj

    def symbol_w(self, space):
        return self.symbol

    def get_flag(self, space, name):
        # Immediate values are always frozen.
        if name == "frozen?":
            return space.w_true
        return W_Object.get_flag(self, space, name)

    def str_w(self, space):
        return self.symbol

    @classdef.singleton_method("all_symbols")
    def singleton_method_all_symbols(self, space):
        return space.newarray(space.symbol_cache.values())

    # Symbols are unique: identity, not Comparable#== (Ruby, with a rescue).
    @classdef.method("==")
    @classdef.method("===")
    def method_eq(self, space, w_other):
        return space.newbool(self is w_other)

    @classdef.method("extend")
    @classdef.method("singleton_class")
    def method_singleton_class(self, space):
        raise space.error(space.w_TypeError, "can't define singleton")

    # Matching goes through String's methods, called from RPython so that
    # $~ is set in the calling Ruby frame.
    @classdef.method("=~")
    def method_match_operator(self, space, w_pattern):
        return space.send(space.newstr_fromstr(self.symbol), "=~", [w_pattern])

    @classdef.method("match")
    def method_match(self, space, args_w, block):
        from topaz.objects.stringobject import W_StringObject
        w_str = space.newstr_fromstr(self.symbol)
        assert isinstance(w_str, W_StringObject)
        if len(args_w) == 0 or len(args_w) > 2:
            raise space.error(space.w_ArgumentError,
                "wrong number of arguments (given %d, expected 1..2)" % len(args_w))
        w_pos = args_w[1] if len(args_w) == 2 else None
        return w_str.method_match(space, args_w[0], w_pos, block)

    @classdef.method("match?")
    def method_matchp(self, space, args_w):
        return space.send(space.newstr_fromstr(self.symbol), "match?", args_w)

    @classdef.method("[]")
    @classdef.method("slice")
    def method_subscript(self, space, args_w):
        return space.send(space.newstr_fromstr(self.symbol), "[]", args_w)

    @classdef.method("to_s")
    def method_to_s(self, space):
        return space.newstr_fromstr(self.symbol)

    @classdef.method("inspect")
    def method_inspect(self, space):
        if symbol_needs_quotes(self.symbol):
            return space.newstr_fromstr(":" + inspect_string(self.symbol))
        return space.newstr_fromstr(":" + self.symbol)

    @classdef.method("length")
    @classdef.method("size")
    def method_size(self, space):
        return space.newint(len(self.symbol))

    @classdef.method("empty?")
    def method_emptyp(self, space):
        return space.newbool(not self.symbol)

    @classdef.method("<=>")
    def method_comparator(self, space, w_other):
        if not space.is_kind_of(w_other, space.w_symbol):
            return space.w_nil
        s1 = self.symbol
        s2 = space.symbol_w(w_other)
        if s1 < s2:
            return space.newint(-1)
        elif s1 == s2:
            return space.newint(0)
        elif s1 > s2:
            return space.newint(1)

    @classdef.method("downcase")
    def method_downcase(self, space):
        return space.newsymbol(self.symbol.lower())

    @classdef.method("upcase")
    def method_upcase(self, space):
        return space.newsymbol(self.symbol.upper())
