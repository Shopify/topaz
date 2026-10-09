import copy
import string
import math

from rpython.rlib import jit
from rpython.rlib.objectmodel import newlist_hint, compute_hash, specialize
from rpython.rlib.rarithmetic import intmask, ovfcheck, r_ulonglong, longlongmask
from rpython.rlib.rbigint import rbigint
from rpython.rlib.rerased import new_static_erasing_pair
from rpython.rlib.rsre import rsre_core
from rpython.rlib.rstring import split, startswith, StringBuilder

from topaz.coerce import Coerce
from topaz.module import ClassDef, check_frozen
from topaz.modules.comparable import Comparable
from topaz.objects.objectobject import W_Object
from topaz.objects.regexpobject import W_MatchDataObject
from topaz.utils.formatting import StringFormatter


RADIX_MAP = {
    "X": 16,
    "x": 16,

    "D": 10,
    "d": 10,

    "O": 8,
    "o": 8,

    "B": 2,
    "b": 2,
}

INSPECT_ESCAPES = {
    "\n": "\\n", "\t": "\\t", "\r": "\\r", "\f": "\\f", "\v": "\\v",
    "\b": "\\b", "\a": "\\a", "\x1b": "\\e", '"': '\\"', "\\": "\\\\",
}

HEX_DIGITS = "0123456789ABCDEF"

unpack_utf8_driver = jit.JitDriver(greens=[], reds="auto", name="String#unpack(U)")


def _utf8_sequence_length(s, i):
    """The length of the valid UTF-8 sequence starting at s[i], or 0."""
    c = ord(s[i])
    if c < 0x80:
        return 1
    elif 0xc2 <= c <= 0xdf:
        length = 2
    elif 0xe0 <= c <= 0xef:
        length = 3
    elif 0xf0 <= c <= 0xf4:
        length = 4
    else:
        return 0
    if i + length > len(s):
        return 0
    for j in range(i + 1, i + length):
        if not (0x80 <= ord(s[j]) <= 0xbf):
            return 0
    c1 = ord(s[i + 1])
    if c == 0xe0 and c1 < 0xa0:       # overlong
        return 0
    if c == 0xed and c1 > 0x9f:       # surrogates
        return 0
    if c == 0xf0 and c1 < 0x90:       # overlong
        return 0
    if c == 0xf4 and c1 > 0x8f:       # beyond U+10FFFF
        return 0
    return length


def inspect_string(s):
    """String#inspect for a UTF-8 string."""
    result = ['"']
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in INSPECT_ESCAPES:
            result.append(INSPECT_ESCAPES[c])
            i += 1
        elif c == "#" and i + 1 < n and s[i + 1] in "{$@":
            # Keep "#{" from reading as interpolation.
            result.append("\\#")
            i += 1
        elif ord(c) < 0x20 or ord(c) == 0x7f:
            code = ord(c)
            result.append("\\u00")
            result.append(HEX_DIGITS[code >> 4])
            result.append(HEX_DIGITS[code & 0xf])
            i += 1
        elif ord(c) < 0x80:
            result.append(c)
            i += 1
        else:
            length = _utf8_sequence_length(s, i)
            if length == 0:
                code = ord(c)
                result.append("\\x")
                result.append(HEX_DIGITS[code >> 4])
                result.append(HEX_DIGITS[code & 0xf])
                i += 1
            else:
                end = i + length
                assert end >= 0
                result.append(s[i:end])
                i = end
    result.append('"')
    return "".join(result)


TR_KEEP = 0
TR_REPLACE = 1
TR_DELETE = 2


class InvalidTrRange(Exception):
    def __init__(self, start, end):
        self.start = start
        self.end = end


def tr_range_error(space, error):
    return space.error(space.w_ArgumentError,
        'invalid range "%s-%s" in string transliteration' %
        (error.start, error.end))


def expand_tr_set(space, source, allow_negate):
    try:
        return expand_tr_set_raw(source, allow_negate)
    except InvalidTrRange as error:
        raise tr_range_error(space, error)


def expand_tr_set_raw(source, allow_negate):
    """A tr character set as a list of characters, and whether it is
    negated (a leading ^ with more after it)."""
    negate = False
    start = 0
    if allow_negate and len(source) > 1 and source[0] == "^":
        negate = True
        start = 1
    chars = []
    i = start
    n = len(source)
    while i < n:
        c = source[i]
        if c == "\\" and i + 1 < n:
            chars.append(source[i + 1])
            i += 2
        elif i + 2 < n and source[i + 1] == "-":
            lo = ord(c)
            hi = ord(source[i + 2])
            if lo > hi:
                raise InvalidTrRange(c, source[i + 2])
            for x in range(lo, hi + 1):
                chars.append(chr(x))
            i += 3
        else:
            chars.append(c)
            i += 1
    return chars, negate


@jit.dont_look_inside
def translate_string(string, source, replacement, squeeze):
    """String#tr and #tr_s: the translated characters, or None when
    nothing changes."""
    src, negate = expand_tr_set_raw(source, True)
    repl, _ = expand_tr_set_raw(replacement, False)
    # kinds[c] is KEEP, REPLACE (with chars[c]) or DELETE.
    kinds = [TR_KEEP] * 256
    chars = ["\0"] * 256
    if negate:
        present = [False] * 256
        for c in src:
            present[ord(c)] = True
        for i in range(256):
            if not present[i]:
                if repl:
                    kinds[i] = TR_REPLACE
                    chars[i] = repl[len(repl) - 1]
                else:
                    kinds[i] = TR_DELETE
    else:
        for i in range(len(src)):
            c = ord(src[i])
            if not repl:
                kinds[c] = TR_DELETE
            else:
                kinds[c] = TR_REPLACE
                chars[c] = repl[i] if i < len(repl) else repl[len(repl) - 1]
    new_string = []
    changed = False
    has_last = False
    last = "\0"
    for char in string:
        kind = kinds[ord(char)]
        if kind == TR_KEEP:
            new_string.append(char)
            has_last = False
            continue
        if kind == TR_DELETE:
            changed = True
            continue
        repl_char = chars[ord(char)]
        if squeeze and has_last and repl_char == last:
            changed = True
            continue
        if repl_char != char:
            changed = True
        new_string.append(repl_char)
        has_last = True
        last = repl_char
    return new_string if changed else None


@jit.dont_look_inside
def scan_integer_prefix(s, radix, is_radix):
    i = 0
    length = len(s)
    while i < length:
        if not s[i].isspace():
            break
        i += 1
    neg = i < length and s[i] == "-"
    if neg:
        i += 1
    if i < length and s[i] == "+":
        i += 1
    if i < length and s[i] == "0":
        if i + 1 < length:
            try:
                r = RADIX_MAP[s[i + 1]]
            except KeyError:
                if radix == 0:
                    radix = 8
            else:
                if not is_radix or radix == r or radix == 0:
                    radix = r
                    i += 2
    if radix == 0:
        radix = 10
    return neg, i, radix


@jit.dont_look_inside
def justify_string(value, pad_len, padstr, left):
    chars = []
    if left:
        chars += value
    for i in xrange(pad_len / len(padstr)):
        chars += padstr
    chars += padstr[:pad_len % len(padstr) + 1]
    if not left:
        chars += value
    return chars


def utf8_char_length(string, pos):
    """The number of bytes in the UTF-8 character at `pos`, or 1."""
    if pos >= len(string):
        return 1
    c = ord(string[pos])
    if c >= 0xf0:
        n = 4
    elif c >= 0xe0:
        n = 3
    elif c >= 0xc0:
        n = 2
    else:
        n = 1
    if n > len(string) - pos:
        n = len(string) - pos
    if n < 1:
        n = 1
    assert n >= 1
    return n


@specialize.argtype(0, 1)
@jit.dont_look_inside
def compare_affix(value, affix, offset):
    # Three mutable-storage specializations (str/list, list/str, list/list).
    # Keep character-dependent exits out of the JIT trace.
    # Not elidable: either storage may be a list mutated in place.
    for i in range(len(affix)):
        if value[offset + i] != affix[i]:
            return False
    return True


@jit.elidable
@jit.dont_look_inside
def ascii_only_str(value):
    for char in value:
        if ord(char) >= 0x80:
            return False
    return True


@jit.dont_look_inside
def ascii_only_list(value):
    # The same list can be modified between calls: this is not elidable.
    for char in value:
        if ord(char) >= 0x80:
            return False
    return True


@specialize.argtype(0)
@jit.dont_look_inside
def unpack_hex(value, pos, digits, high_first):
    # Specialize for raw str/list storage, but keep data-dependent iteration
    # out of the caller's trace. Mutable storage must be read on every call.
    alphabet = "0123456789abcdef"
    first_shift = 4 if high_first else 0
    second_shift = 4 - first_shift
    builder = StringBuilder(digits)
    pairs = digits // 2
    end = pos + pairs
    while pos < end:
        byte = ord(value[pos])
        builder.append(alphabet[(byte >> first_shift) & 15])
        builder.append(alphabet[(byte >> second_shift) & 15])
        pos += 1
    if digits & 1:
        builder.append(alphabet[(ord(value[pos]) >> first_shift) & 15])
    return builder.build()


@specialize.argtype(0)
@jit.look_inside_iff(lambda value, pos, size, big:
                     jit.isconstant(size) and jit.isconstant(big))
def unpack_integer(value, pos, size, big):
    # Only fixed-width reads (1/2/4/8 bytes) may expand in a caller trace.
    # Dynamic format reads stay outside it; repetition counts are handled
    # separately by the Ruby dispatcher.
    result = r_ulonglong(0)
    if big:
        for i in range(size):
            result = (result << 8) | r_ulonglong(ord(value[pos + i]))
    else:
        for i in range(size - 1, -1, -1):
            result = (result << 8) | r_ulonglong(ord(value[pos + i]))
    return result


@specialize.argtype(0)
@jit.dont_look_inside
def base64_encode(value, pos, length):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    groups = length // 3
    tail = length % 3
    capacity = ovfcheck((groups + (tail != 0)) * 4)
    builder = StringBuilder(capacity)
    end = pos + groups * 3
    while pos < end:
        b0 = ord(value[pos])
        b1 = ord(value[pos + 1])
        b2 = ord(value[pos + 2])
        builder.append(alphabet[b0 >> 2])
        builder.append(alphabet[((b0 & 3) << 4) | (b1 >> 4)])
        builder.append(alphabet[((b1 & 15) << 2) | (b2 >> 6)])
        builder.append(alphabet[b2 & 63])
        pos += 3
    if tail:
        b0 = ord(value[pos])
        builder.append(alphabet[b0 >> 2])
        if tail == 1:
            builder.append(alphabet[(b0 & 3) << 4])
            builder.append("==")
        else:
            b1 = ord(value[pos + 1])
            builder.append(alphabet[((b0 & 3) << 4) | (b1 >> 4)])
            builder.append(alphabet[(b1 & 15) << 2])
            builder.append("=")
    return builder.build()


class StringStrategy(object):
    def __init__(self, space):
        pass

    def __deepcopy__(self, memo):
        memo[id(self)] = result = object.__new__(self.__class__)
        return result


class ConstantStringStrategy(StringStrategy):
    erase, unerase = new_static_erasing_pair("constant")

    def str_w(self, storage):
        return self.unerase(storage)

    def liststr_w(self, storage):
        strvalue = self.unerase(storage)
        return [c for c in strvalue]

    def length(self, storage):
        return len(self.unerase(storage))

    def ascii_only(self, storage):
        return ascii_only_str(self.unerase(storage))

    def unpack_hex(self, storage, pos, digits, high_first):
        return unpack_hex(self.unerase(storage), pos, digits, high_first)

    def unpack_integer(self, storage, pos, size, big):
        return unpack_integer(self.unerase(storage), pos, size, big)

    def base64_encode(self, storage, pos, length):
        return base64_encode(self.unerase(storage), pos, length)

    def getitem(self, storage, idx):
        return self.unerase(storage)[idx]

    def compare_affix(self, storage, w_affix, offset):
        value = self.unerase(storage)
        strategy = w_affix.strategy
        if isinstance(strategy, ConstantStringStrategy):
            # Both storages are immutable: the existing RPython helper is
            # elidable, while its character loop stays outside the trace.
            return startswith(value, strategy.unerase(w_affix.str_storage), offset)
        assert isinstance(strategy, MutableStringStrategy)
        return compare_affix(value, strategy.unerase(w_affix.str_storage), offset)

    def getslice(self, space, storage, start, end):
        return space.newstr_fromstr(self.unerase(storage)[start:end])

    def hash(self, storage):
        return compute_hash(self.unerase(storage))

    def copy(self, storage):
        return storage

    def to_mutable(self, space, s):
        s.strategy = strategy = space.fromcache(MutableStringStrategy)
        s.str_storage = strategy.erase(self.liststr_w(s.str_storage))

    def extend_into(self, src_storage, dst_storage):
        value = self.unerase(src_storage)
        if len(value) == 1:
            # Let the JIT keep table[index]'s one-byte string virtual.
            dst_storage.append(value[0])
        else:
            dst_storage += value

    def mul(self, space, storage, times):
        return space.newstr_fromstr(self.unerase(storage) * times)


class MutableStringStrategy(StringStrategy):
    erase, unerase = new_static_erasing_pair("mutable")

    def str_w(self, storage):
        return "".join(self.unerase(storage))

    def liststr_w(self, storage):
        return self.unerase(storage)

    def length(self, storage):
        return len(self.unerase(storage))

    def ascii_only(self, storage):
        return ascii_only_list(self.unerase(storage))

    def unpack_hex(self, storage, pos, digits, high_first):
        return unpack_hex(self.unerase(storage), pos, digits, high_first)

    def unpack_integer(self, storage, pos, size, big):
        return unpack_integer(self.unerase(storage), pos, size, big)

    def base64_encode(self, storage, pos, length):
        return base64_encode(self.unerase(storage), pos, length)

    def getitem(self, storage, idx):
        return self.unerase(storage)[idx]

    def compare_affix(self, storage, w_affix, offset):
        value = self.unerase(storage)
        strategy = w_affix.strategy
        if isinstance(strategy, ConstantStringStrategy):
            return compare_affix(value, strategy.unerase(w_affix.str_storage), offset)
        assert isinstance(strategy, MutableStringStrategy)
        return compare_affix(value, strategy.unerase(w_affix.str_storage), offset)

    def getslice(self, space, storage, start, end):
        return space.newstr_fromchars(self.unerase(storage)[start:end])

    def delslice(self, space, storage, start, end):
        del self.unerase(storage)[start:end]

    def hash(self, storage):
        storage = self.unerase(storage)
        length = len(storage)
        if length == 0:
            return -1
        x = ord(storage[0]) << 7
        i = 0
        while i < length:
            x = intmask((1000003 * x) ^ ord(storage[i]))
            i += 1
        x ^= length
        return intmask(x)

    def copy(self, storage):
        return self.erase(self.unerase(storage)[:])

    def to_mutable(self, space, s):
        pass

    def extend_into(self, src_storage, dst_storage):
        dst_storage += self.unerase(src_storage)

    def clear(self, s):
        storage = self.unerase(s.str_storage)
        del storage[:]

    def mul(self, space, storage, times):
        return space.newstr_fromchars(self.unerase(storage) * times)

    def reverse(self, storage):
        storage = self.unerase(storage)
        storage.reverse()

    def swapcase(self, storage):
        storage = self.unerase(storage)
        changed = False
        for i, c in enumerate(storage):
            if ord("A") <= ord(c) <= ord("Z"):
                new_c = c.lower()
                changed = True
            elif ord("a") <= ord(c) <= ord("z"):
                new_c = c.upper()
                changed = True
            else:
                new_c = c
            storage[i] = new_c
        return changed

    def downcase(self, storage):
        storage = self.unerase(storage)
        changed = False
        for i, c in enumerate(storage):
            new_c = c.lower()
            changed |= (c != new_c)
            storage[i] = new_c
        return changed

    def upcase(self, storage):
        storage = self.unerase(storage)
        changed = False
        for i, c in enumerate(storage):
            new_c = c.upper()
            changed |= (c != new_c)
            storage[i] = new_c
        return changed

    def capitalize(self, storage):
        storage = self.unerase(storage)
        changed = False
        for i, c in enumerate(storage):
            if i == 0:
                new_c = c.upper()
            else:
                new_c = c.lower()
            changed |= (c != new_c)
            storage[i] = new_c
        return changed

    def chomp(self, storage, newline=None):
        storage = self.unerase(storage)
        changed = False
        linebreaks = ["\n", "\r"]
        if len(storage) == 0:
            return changed
        elif newline is not None and len(newline) == 0:
            ch = storage[-1]
            i = len(storage) - 1
            if ch != "\r":
                while i >= 1 and ch in linebreaks:
                    i -= 1
                    ch = storage[i]
            if i < len(storage) - 1:
                i += 1
                changed = True
                if i > 0:
                    del storage[i:]
                else:
                    del storage[:]
        elif newline is not None and len(storage) >= len(newline):
            for i in xrange(len(newline) - 1, -1, -1):
                if newline[i] != storage[len(storage) - len(newline) + i]:
                    return changed
            start = len(storage) - len(newline)
            assert start >= 0
            del storage[start:]
            changed = True
        elif newline is None:
            ch = storage[-1]
            i = len(storage) - 1
            while i >= 0 and linebreaks and ch in linebreaks:
                linebreaks.remove(ch)
                i -= 1
                ch = storage[i]
            if i < len(storage) - 1:
                i += 1
                changed = True
                if i > 0:
                    del storage[i:]
                else:
                    del storage[:]
        return changed

    def chop(self, storage):
        storage = self.unerase(storage)
        if len(storage) == 0:
            return False
        elif storage[-1] == "\n" and len(storage) >= 2 and storage[-2] == "\r":
            idx = len(storage) - 2
            assert idx >= 0
            del storage[idx:]
            return True
        else:
            del storage[-1]
            return True

    def succ(self, storage):
        storage = self.unerase(storage)
        if len(storage) == 0:
            return

        carry = "\0"
        has_alnums = False
        last_alnum = 0
        start = len(storage) - 1

        while start >= 0:
            ch = storage[start]
            if ch in string.letters or ch in string.digits:
                has_alnums = True
                if ch == "9":
                    carry = "1"
                    storage[start] = "0"
                elif ch == "z":
                    carry = "a"
                    storage[start] = "a"
                elif ch == "Z":
                    carry = "A"
                    storage[start] = "A"
                else:
                    storage[start] = chr(ord(ch) + 1)
                    carry = "\0"

                if carry == "\0":
                    break
                last_alnum = start
            start -= 1

        if not has_alnums:
            start = len(storage) - 1
            carry = "\1"

            while start >= 0:
                ch = storage[start]
                if ord(ch) >= 255:
                    storage[start] = "\0"
                else:
                    storage[start] = chr(ord(ch) + 1)
                    break
                start -= 1

        if start < 0 and carry != "\0":
            last_alnum_ch = storage[last_alnum]
            storage[last_alnum] = carry
            storage.insert(last_alnum + 1, last_alnum_ch)

    def insert(self, storage, idx, other):
        storage = self.unerase(storage)
        for char in other:
            storage.insert(idx, char)
            idx += 1

    def replaceitem(self, storage, idx, char):
        storage = self.unerase(storage)
        storage[idx] = char

    def strip(self, storage):
        storage = self.unerase(storage)
        if not storage:
            return False

        shift = 0
        while shift < len(storage) and storage[shift].isspace():
            shift += 1
        if shift == len(storage):
            del storage[:]
            return True

        pop = len(storage)
        while pop > 0 and storage[pop - 1].isspace() or storage[pop - 1] == '\0':
            pop -= 1

        if pop < len(storage) or shift > 0:
            end = pop
            new_len = end - shift
            assert end >= 0
            assert new_len >= 0
            storage[0:new_len] = storage[shift:end]
            del storage[new_len:]
            return True
        else:
            return False



@jit.unroll_safe
def _string_new_keywords(space, w_kwargs):
    """The encoding: value of String.new's keywords (None when absent;
    nil when given as nil), checking the other keywords."""
    w_encoding = None
    for w_key in w_kwargs.strategy.keys(w_kwargs.dict_storage):
        key = None
        if space.is_kind_of(w_key, space.w_symbol):
            key = space.symbol_w(w_key)
        if key == "encoding":
            w_encoding = w_kwargs.getitem(w_key)
        elif key != "capacity":
            raise space.error(space.w_ArgumentError,
                "unknown keyword: %s" % space.str_w(space.send(w_key, "inspect")))
    return w_encoding

class W_StringObject(W_Object):
    classdef = ClassDef("String", W_Object.classdef)
    classdef.include_module(Comparable)

    def __init__(self, space, storage, strategy, klass=None):
        W_Object.__init__(self, space, klass)
        self.str_storage = storage
        self.strategy = strategy
        # The encoding tag: None is UTF-8, the default, so that the common
        # string carries nothing. Encoding objects themselves are defined
        # by lib-topaz/encoding.rb.
        self.w_encoding = None

    def __deepcopy__(self, memo):
        obj = super(W_StringObject, self).__deepcopy__(memo)
        obj.str_storage = copy.deepcopy(self.str_storage, memo)
        obj.strategy = copy.deepcopy(self.strategy, memo)
        obj.w_encoding = copy.deepcopy(self.w_encoding, memo)
        return obj

    @staticmethod
    def newstr_fromstr(space, strvalue):
        strategy = space.fromcache(ConstantStringStrategy)
        storage = strategy.erase(strvalue)
        return W_StringObject(space, storage, strategy)

    @staticmethod
    @jit.look_inside_iff(lambda space, strs_w: jit.isconstant(len(strs_w)))
    def newstr_fromstrs(space, strs_w):
        total_length = 0
        for w_item in strs_w:
            assert isinstance(w_item, W_StringObject)
            total_length += w_item.length()

        storage = newlist_hint(total_length)
        for w_item in strs_w:
            assert isinstance(w_item, W_StringObject)
            w_item.strategy.extend_into(w_item.str_storage, storage)
        return space.newstr_fromchars(storage)

    @staticmethod
    def newstr_fromchars(space, chars):
        strategy = space.fromcache(MutableStringStrategy)
        storage = strategy.erase(chars)
        return W_StringObject(space, storage, strategy)

    def str_w(self, space):
        return self.strategy.str_w(self.str_storage)

    def symbol_w(self, space):
        return self.str_w(space)

    def liststr_w(self, space):
        return self.strategy.liststr_w(self.str_storage)

    def length(self):
        return self.strategy.length(self.str_storage)

    def copy(self, space):
        w_res = W_StringObject(space, self.strategy.copy(self.str_storage), self.strategy)
        w_res.w_encoding = self.w_encoding
        return w_res

    def replace(self, space, chars):
        strategy = space.fromcache(MutableStringStrategy)
        self.str_storage = strategy.erase(chars)
        self.strategy = strategy

    def extend(self, space, w_other):
        self.strategy.to_mutable(space, self)
        strategy = self.strategy
        assert isinstance(strategy, MutableStringStrategy)
        storage = strategy.unerase(self.str_storage)
        w_other.strategy.extend_into(w_other.str_storage, storage)

    def clear(self, space):
        self.strategy.to_mutable(space, self)
        self.strategy.clear(self)

    def tr_trans(self, space, source, replacement, squeeze):
        try:
            return translate_string(space.str_w(self), source, replacement, squeeze)
        except InvalidTrRange as error:
            raise tr_range_error(space, error)

    @classdef.singleton_method("allocate")
    def singleton_method_allocate(self, space):
        strategy = space.fromcache(ConstantStringStrategy)
        storage = strategy.erase("")
        return W_StringObject(space, storage, strategy, self)

    @classdef.method("initialize")
    @check_frozen()
    def method_initialize(self, space, args_w):
        """String.new(str = "", encoding: nil, capacity: nil). The copy of
        str keeps its encoding tag; with no str the string is binary, as in
        CRuby. capacity is accepted and ignored.

        Kept free of loops so the JIT inlines it and a String.new whose
        result does not escape stays virtual."""
        from topaz.objects.hashobject import W_HashObject
        w_encoding = None
        if args_w:
            w_last = args_w[-1]
            if isinstance(w_last, W_HashObject) and w_last.is_keywords:
                end = len(args_w) - 1
                assert end >= 0
                args_w = args_w[:end]
                w_encoding = _string_new_keywords(space, w_last)
        if len(args_w) > 1:
            raise space.error(space.w_ArgumentError,
                "wrong number of arguments (given %d, expected 0..1)" % len(args_w))
        if args_w:
            w_s = space.convert_type(args_w[0], space.w_string, "to_str")
            assert isinstance(w_s, W_StringObject)
            self.strategy = w_s.strategy
            self.str_storage = w_s.strategy.copy(w_s.str_storage)
            self.w_encoding = w_s.w_encoding
        if w_encoding is not None:
            self.force_encoding(space, w_encoding)
        elif not args_w:
            self.w_encoding = space.encoding_binary()
        return self

    def force_encoding(self, space, w_enc):
        from topaz.objects.encodingobject import W_EncodingObject
        if not isinstance(w_enc, W_EncodingObject):
            w_enc = space.send(space.getclassfor(W_EncodingObject), "find", [w_enc])
        if w_enc is space.encoding_utf8():
            self.w_encoding = None
        else:
            self.w_encoding = w_enc

    @classdef.method("encoding")
    def method_encoding(self, space):
        w_enc = self.w_encoding
        if w_enc is None:
            return space.encoding_utf8()
        return w_enc

    @classdef.method("force_encoding")
    @check_frozen()
    def method_force_encoding(self, space, w_enc):
        self.force_encoding(space, w_enc)
        return self

    @classdef.method("b")
    def method_b(self, space):
        # A plain String copy of the bytes, tagged binary; in Ruby this
        # was dup + force_encoding, two more frames per call.
        w_res = W_StringObject(space, self.strategy.copy(self.str_storage), self.strategy)
        w_res.w_encoding = space.encoding_binary()
        return w_res

    @classdef.method("initialize_copy")
    def method_initialize_copy(self, space, w_other):
        assert isinstance(w_other, W_StringObject)
        self.strategy = w_other.strategy
        self.str_storage = w_other.strategy.copy(w_other.str_storage)
        self.w_encoding = w_other.w_encoding
        return self

    # In RPython rather than through insert or []=, which subclasses such as
    # ActiveSupport::SafeBuffer override.
    @classdef.method("replace")
    @check_frozen()
    def method_replace(self, space, w_other):
        w_other = space.convert_type(w_other, space.w_string, "to_str")
        assert isinstance(w_other, W_StringObject)
        if w_other is not self:
            self.strategy = w_other.strategy
            self.str_storage = w_other.strategy.copy(w_other.str_storage)
            self.w_encoding = w_other.w_encoding
        return self

    @classdef.method("to_str")
    @classdef.method("to_s")
    def method_to_s(self, space):
        if space.getnonsingletonclass(self) is space.w_string:
            return self
        # A String subclass gives a plain String copy (keeping the encoding).
        w_copy = space.newstr_fromstr(space.str_w(self))
        w_copy.w_encoding = self.w_encoding
        return w_copy

    @classdef.method("ord")
    def method_ord(self, space):
        if self.length() == 0:
            raise space.error(space.w_ArgumentError, "empty string")
        return space.newint(ord(self.strategy.getitem(self.str_storage, 0)))

    @classdef.method("inspect")
    def method_inspect(self, space):
        s = space.newstr_fromstr(inspect_string(self.str_w(space)))
        space.infect(s, self)
        return s

    @classdef.method("+")
    def method_plus(self, space, w_obj):
        w_other = space.convert_type(w_obj, space.w_string, "to_str")
        assert isinstance(w_other, W_StringObject)
        total_size = self.length() + w_other.length()
        s = space.newstr_fromchars(newlist_hint(total_size))
        s.extend(space, self)
        s.extend(space, w_other)
        if self.w_encoding is w_other.w_encoding:
            s.w_encoding = self.w_encoding
        space.infect(s, self)
        space.infect(s, w_other)
        return s

    @classdef.method("*", times="int")
    def method_times(self, space, times):
        if times < 0:
            raise space.error(space.w_ArgumentError, "negative argument")
        res = self.strategy.mul(space, self.str_storage, times)
        space.infect(res, self)
        res.w_encoding = self.w_encoding
        return res

    @classdef.method("<<")
    @classdef.method("concat")
    @check_frozen()
    def method_lshift(self, space, w_other):
        if space.is_kind_of(w_other, space.w_fixnum):
            w_other = space.send(w_other, "chr")
        else:
            w_other = space.convert_type(w_other, space.w_string, "to_str")
        assert isinstance(w_other, W_StringObject)
        self.extend(space, w_other)
        space.infect(self, w_other)
        return self

    @classdef.method("bytesize")
    @classdef.method("size")
    @classdef.method("length")
    def method_length(self, space):
        return space.newint(self.length())

    @classdef.method("start_with?")
    def method_start_with(self, space, args_w):
        if len(args_w) == 1:
            return space.newbool(self.matches_affix(space, args_w[0], False))
        return space.newbool(self.matches_any_affix(space, args_w, False))

    @classdef.method("end_with?")
    def method_end_with(self, space, args_w):
        if len(args_w) == 1:
            return space.newbool(self.matches_affix(space, args_w[0], True))
        return space.newbool(self.matches_any_affix(space, args_w, True))

    @jit.look_inside_iff(lambda self, space, args_w, from_end:
                         jit.isconstant(len(args_w)) and len(args_w) <= 4)
    def matches_any_affix(self, space, args_w, from_end):
        for w_affix in args_w:
            if self.matches_affix(space, w_affix, from_end):
                return True
        return False

    def matches_affix(self, space, w_affix, from_end):
        if not isinstance(w_affix, W_StringObject):
            # Keep the permissive conversion of the former Ruby methods.
            w_affix = space.convert_type(
                w_affix, space.w_string, "to_str", raise_error=False)
            if w_affix is space.w_nil:
                return False
            assert isinstance(w_affix, W_StringObject)
        # Conversion may have mutated the receiver; read lengths afterwards.
        length = w_affix.length()
        offset = self.length() - length
        if offset < 0:
            return False
        if not from_end:
            offset = 0
        return self.strategy.compare_affix(self.str_storage, w_affix, offset)

    @classdef.method("hash")
    def method_hash(self, space):
        return space.newint(self.strategy.hash(self.str_storage))

    @classdef.method("empty?")
    def method_emptyp(self, space):
        return space.newbool(self.length() == 0)

    @classdef.method("ascii_only?")
    def method_ascii_only(self, space):
        return space.newbool(self.strategy.ascii_only(self.str_storage))

    @classdef.method("__topaz_base64_encode", pos="int", length="int")
    def method_base64_encode(self, space, pos, length):
        if pos < 0 or pos > self.length() or length < 0 or length > self.length() - pos:
            raise space.error(space.w_ArgumentError, "invalid base64 slice")
        try:
            value = self.strategy.base64_encode(self.str_storage, pos, length)
        except OverflowError:
            raise space.error(space.w_RangeError, "base64 output too large")
        return space.newstr_fromstr(value)

    @classdef.method("__topaz_unpack_integer", pos="int", size="int")
    def method_unpack_integer(self, space, pos, size, w_big, w_signed):
        if size != 1 and size != 2 and size != 4 and size != 8:
            raise space.error(space.w_ArgumentError, "invalid integer width")
        if pos < 0 or pos > self.length():
            raise space.error(space.w_ArgumentError, "invalid integer offset")
        if size > self.length() - pos:
            return space.w_nil
        value = self.strategy.unpack_integer(
            self.str_storage, pos, size, space.is_true(w_big))
        if space.is_true(w_signed):
            shift = (8 - size) * 8
            signed = longlongmask(value << shift) >> shift
            return space.newint_or_bigint(signed)
        return space.newint_or_bigint_fromunsigned(value)

    @classdef.method("__topaz_unpack_hex", pos="int", digits="int")
    def method_unpack_hex(self, space, pos, digits, w_high_first):
        length = self.length()
        if pos < 0 or pos > length or digits < 0 or digits > (length - pos) * 2:
            raise space.error(space.w_ArgumentError, "invalid hexadecimal slice")
        value = self.strategy.unpack_hex(
            self.str_storage, pos, digits, space.is_true(w_high_first))
        return space.newstr_fromstr(value)

    @classdef.method("__topaz_unpack_utf8", count="int")
    def method_unpack_utf8(self, space, count):
        """unpack("U") / unpack("U*") from byte 0: the codepoints of up to
        `count` UTF-8 characters (all of them when count < 0), with
        MRI's errors for malformed input (lib-topaz/pack.rb's Ruby
        decoder handles the other templates)."""
        storage = self.str_storage
        strategy = self.strategy
        length = strategy.length(storage)
        pos = 0
        result_w = []
        while pos < length and count != 0:
            unpack_utf8_driver.jit_merge_point()
            b = ord(strategy.getitem(storage, pos))
            if b < 0x80:
                result_w.append(space.newint(b))
                pos += 1
                count -= 1
                continue
            elif b & 0xe0 == 0xc0:
                n = 1
                cp = b & 0x1f
                minimum = 0x80
            elif b & 0xf0 == 0xe0:
                n = 2
                cp = b & 0x0f
                minimum = 0x800
            elif b & 0xf8 == 0xf0:
                n = 3
                cp = b & 0x07
                minimum = 0x10000
            else:
                raise space.error(space.w_ArgumentError, "malformed UTF-8 character")
            if pos + n >= length:
                raise space.error(space.w_ArgumentError,
                    "malformed UTF-8 character (expected %d bytes, given %d bytes)"
                    % (n + 1, length - pos))
            for k in range(1, n + 1):
                c = ord(strategy.getitem(storage, pos + k))
                if c & 0xc0 != 0x80:
                    raise space.error(space.w_ArgumentError, "malformed UTF-8 character")
                cp = (cp << 6) | (c & 0x3f)
            if cp < minimum:
                raise space.error(space.w_ArgumentError, "redundant UTF-8 sequence")
            result_w.append(space.newint(cp))
            pos += n + 1
            count -= 1
        return space.newarray(result_w)

    @classdef.method("__topaz_escape_html")
    def method_escape_html(self, space):
        """The loop behind CGI.escapeHTML and ERB::Escape.html_escape
        (lib-ruby/ext/erb/escape.rb): self when nothing needs escaping,
        otherwise a new String with ' & " < > replaced."""
        s = space.str_w(self)
        n = len(s)
        i = 0
        while i < n:
            c = s[i]
            if c == "&" or c == "<" or c == ">" or c == '"' or c == "'":
                break
            i += 1
        if i == n:
            return self
        builder = StringBuilder(n + 16)
        builder.append_slice(s, 0, i)
        while i < n:
            c = s[i]
            if c == "&":
                builder.append("&amp;")
            elif c == "<":
                builder.append("&lt;")
            elif c == ">":
                builder.append("&gt;")
            elif c == '"':
                builder.append("&quot;")
            elif c == "'":
                builder.append("&#39;")
            else:
                builder.append(c)
            i += 1
        return space.newstr_fromstr(builder.build())

    @classdef.method("[]")
    @classdef.method("slice")
    @classdef.method("byteslice")
    def method_subscript(self, space, w_idx, w_count=None):
        if space.is_kind_of(w_idx, space.w_string):
            if space.send(self, "include?", [w_idx]):
                return w_idx
            else:
                return space.w_nil

        if space.is_kind_of(w_idx, space.w_regexp):
            w_match = space.send(w_idx, "match", [self])
            if w_match is space.w_nil:
                return space.w_nil
            elif not w_count:
                return space.send(w_match, "[]", [space.newint(0)])
            else:
                return space.send(w_match, "[]", [w_count])

        start, end, as_range, nil = space.subscript_access(self.length(), w_idx, w_count=w_count)
        if nil:
            return space.w_nil
        elif as_range:
            assert start >= 0
            assert end >= 0
            return self.strategy.getslice(space, self.str_storage, start, end)
        else:
            return space.newstr_fromstr(self.strategy.getitem(self.str_storage, start))

    @classdef.method("[]=")
    def method_subscript(self, space, w_idx, w_count, w_other=None):
        if w_other is None:
            w_other = w_count
            w_count = None

        other = Coerce.str(space, w_other)
        start_idx = -1
        end_idx = -1
        if space.is_kind_of(w_idx, space.w_string):
            other_str = space.str_w(w_idx)
            start_idx = space.str_w(self).find(other_str)
            end_idx = start_idx + len(other_str)
        elif space.is_kind_of(w_idx, space.w_regexp):
            ctx = w_idx.make_ctx(space.str_w(self))
            if self.search_context(space, w_idx, ctx):
                if w_count is None:
                    start_idx = ctx.match_start
                    end_idx = ctx.match_end
                elif space.is_kind_of(w_count, space.w_string):
                    raise space.error(
                        space.w_NotImplementedError,
                        "string subscript replace with regexp and named group"
                    )
                else:
                    groupnum = Coerce.int(space, w_count)
                    try:
                        start_idx, end_idx = ctx.span(groupnum)
                    except IndexError:
                        pass
        else:
            start_idx, end_idx, as_range, nil = space.subscript_access(self.length(), w_idx, w_count=w_count)
            if not w_count and not as_range:
                end_idx = start_idx + 1

        if start_idx < 0 or end_idx < 0:
            raise space.error(space.w_IndexError, "cannot find substring in string to replace")

        self.strategy.to_mutable(space, self)
        self.strategy.delslice(space, self.str_storage, start_idx, end_idx)
        self.strategy.insert(self.str_storage, start_idx, other)
        return self

    @classdef.method("slice!")
    @check_frozen()
    def method_slice_i(self, space, w_idx, w_count=None):
        start, end, as_range, nil = space.subscript_access(self.length(), w_idx, w_count=w_count)
        if nil:
            return space.w_nil
        elif as_range:
            assert start >= 0
            assert end >= 0
            self.strategy.to_mutable(space, self)
            w_string = self.strategy.getslice(space, self.str_storage, start, end)
            self.strategy.delslice(space, self.str_storage, start, end)
            return w_string
        else:
            assert start >= 0
            self.strategy.to_mutable(space, self)
            w_string = self.strategy.getslice(space, self.str_storage, start, start + 1)
            self.strategy.delslice(space, self.str_storage, start, start + 1)
            return w_string

    # In RPython: Comparable#== (Ruby, with a rescue) was String#==, and
    # every Hash lookup with a String key calls eql?.
    @classdef.method("==")
    @classdef.method("===")
    def method_eq(self, space, w_other):
        if isinstance(w_other, W_StringObject):
            return space.newbool(space.str_w(self) == space.str_w(w_other))
        if space.respond_to(w_other, "to_str"):
            return space.newbool(space.is_true(space.send(w_other, "==", [self])))
        return space.w_false

    @classdef.method("eql?")
    def method_eqlp(self, space, w_other):
        if isinstance(w_other, W_StringObject):
            return space.newbool(space.str_w(self) == space.str_w(w_other))
        return space.w_false

    @classdef.method("<=>")
    def method_comparator(self, space, w_other):
        if isinstance(w_other, W_StringObject):
            s1 = space.str_w(self)
            s2 = space.str_w(w_other)
            if s1 < s2:
                return space.newint(-1)
            elif s1 == s2:
                return space.newint(0)
            elif s1 > s2:
                return space.newint(1)
        else:
            if space.respond_to(w_other, "to_str") and space.respond_to(w_other, "<=>"):
                tmp = space.send(w_other, "<=>", [self])
                if tmp is not space.w_nil:
                    return space.newint(-space.int_w(tmp))
            return space.w_nil

    @classdef.method("to_sym")
    @classdef.method("intern")
    def method_to_sym(self, space):
        return space.newsymbol(space.str_w(self))

    @classdef.method("clear")
    @check_frozen()
    def method_clear(self, space):
        self.clear(space)
        return self

    @classdef.method("ljust", integer="int", padstr="str")
    def method_ljust(self, space, integer, padstr=" "):
        if not padstr:
            raise space.error(space.w_ArgumentError, "zero width padding")
        elif integer <= self.length():
            return self.copy(space)
        else:
            pad_len = integer - self.length() - 1
            assert pad_len >= 0
            chars = justify_string(space.str_w(self), pad_len, padstr, True)
            return space.newstr_fromchars(chars)

    @classdef.method("rjust", integer="int", padstr="str")
    def method_rjust(self, space, integer, padstr=" "):
        if not padstr:
            raise space.error(space.w_ArgumentError, "zero width padding")
        elif integer <= self.length():
            return self.copy(space)
        else:
            pad_len = integer - self.length() - 1
            assert pad_len >= 0
            chars = justify_string(space.str_w(self), pad_len, padstr, False)
            return space.newstr_fromchars(chars)

    def search_context(self, space, w_regexp, ctx):
        try:
            return w_regexp.rsre_search(ctx)
        except rsre_core.Error, e:
            raise space.error(space.w_RuntimeError, e.msg)

    @classdef.method("find_string", offset="int")
    @classdef.method("index", offset="int")
    def method_index(self, space, w_sub, offset=0):
        string = space.str_w(self)
        length = len(string)
        if offset < 0:
            offset += length
            if offset < 0:
                return space.w_nil
        if offset > length:
            return space.w_nil
        if space.is_kind_of(w_sub, space.w_regexp):
            ctx = w_sub.make_ctx(string, offset=offset)
            if self.search_context(space, w_sub, ctx):
                w_sub.get_match_result(space, ctx, string, found=True)
                return space.newint(ctx.match_start)
            w_sub.get_match_result(space, ctx, string, found=False)
            return space.w_nil
        w_str = space.convert_type(w_sub, space.w_string, "to_str")
        idx = string.find(space.str_w(w_str), offset)
        if idx < 0:
            return space.w_nil
        return space.newint(idx)

    @classdef.method("rindex")
    def method_rindex(self, space, w_sub, w_pos=None):
        string = space.str_w(self)
        length = len(string)
        pos = length
        if w_pos is not None:
            pos = Coerce.int(space, w_pos)
            if pos < 0:
                pos += length
                if pos < 0:
                    return space.w_nil
            if pos > length:
                pos = length
        if space.is_kind_of(w_sub, space.w_regexp):
            ctx = w_sub.make_ctx(string)
            idx = -1
            start = 0
            while start <= pos:
                ctx.reset(start)
                if not self.search_context(space, w_sub, ctx):
                    break
                if ctx.match_start > pos:
                    break
                idx = ctx.match_start
                start = idx + 1
            if idx < 0:
                w_sub.get_match_result(space, ctx, string, found=False)
                return space.w_nil
            ctx.reset(idx)
            self.search_context(space, w_sub, ctx)
            w_sub.get_match_result(space, ctx, string, found=True)
            return space.newint(idx)
        w_str = space.convert_type(w_sub, space.w_string, "to_str")
        sub = space.str_w(w_str)
        stop = pos + len(sub)
        if stop > length:
            stop = length
        assert stop >= 0
        idx = string.rfind(sub, 0, stop)
        if idx < 0:
            return space.w_nil
        return space.newint(idx)

    @classdef.method("split", limit="int")
    def method_split(self, space, w_sep=None, limit=0):
        if w_sep is None:
            res_w = []
            i = 0
            limit -= 1
            s = space.str_w(self)
            while True:
                while i < len(s):
                    if not s[i].isspace():
                        break
                    i += 1
                else:
                    break
                if limit == 0:
                    j = len(s)
                else:
                    j = i + 1
                    while j < len(s) and not s[j].isspace():
                        j += 1
                    limit -= 1
                res_w.append(space.newstr_fromstr(s[i:j]))
                i = j + 1
            return space.newarray(res_w)
        elif space.is_kind_of(w_sep, space.w_string):
            sep = space.str_w(w_sep)
            if sep:
                return space.newarray([
                    space.newstr_fromstr(s) for s in split(space.str_w(self), sep, limit - 1)
                ])
            else:
                if limit:
                    raise space.error(space.w_NotImplementedError, "String#split with empty string and limit")
                return space.newarray([
                    space.newstr_fromstr(self.strategy.getitem(self.str_storage, i))
                    for i in xrange(self.length())
                ])
        elif space.is_kind_of(w_sep, space.w_regexp):
            # This follows rb_str_split_m in CRuby's string.c.
            string = space.str_w(self)
            if limit == 1:
                if not string:
                    return space.newarray([])
                return space.newarray([space.newstr_fromstr(string)])
            results_w = []
            beg = 0
            start = 0
            last_null = False
            i = 1
            ctx = w_sep.make_ctx(string)
            while start <= len(string):
                ctx.reset(start)
                if not self.search_context(space, w_sep, ctx):
                    break
                w_match = w_sep.get_match_result(space, ctx, string, found=True)
                assert isinstance(w_match, W_MatchDataObject)
                end = ctx.match_start
                if start == end and ctx.match_start == ctx.match_end:
                    if not string:
                        results_w.append(space.newstr_fromstr(""))
                        break
                    elif last_null:
                        assert beg >= 0 and start >= beg
                        results_w.append(space.newstr_fromstr(string[beg:start]))
                        beg = start
                    else:
                        if start == len(string):
                            start += 1
                        else:
                            start += utf8_char_length(string, start)
                        last_null = True
                        continue
                else:
                    assert beg >= 0 and end >= beg
                    results_w.append(space.newstr_fromstr(string[beg:end]))
                    beg = start = ctx.match_end
                last_null = False
                for num in xrange(1, w_match.size(), 1):
                    begin, stop = w_match.get_span(num)
                    if begin < 0 or stop < 0:
                        continue
                    results_w.append(space.newstr_fromstr(string[begin:stop]))
                if limit > 0:
                    i += 1
                    if limit <= i:
                        break
            if len(string) > 0 and (limit > 0 or len(string) > beg or limit < 0):
                assert beg >= 0
                results_w.append(space.newstr_fromstr(string[beg:]))
            if limit == 0:
                while results_w and not space.str_w(results_w[-1]):
                    results_w.pop()
            return space.newarray(results_w)

        else:
            raise space.error(
                space.w_TypeError,
                "wrong argument type %s (expected Regexp)" % (
                    space.obj_to_s(space.getclass(w_sep))
                )
            )

    @classdef.method("swapcase!")
    @check_frozen()
    def method_swapcase_i(self, space):
        self.strategy.to_mutable(space, self)
        changed = self.strategy.swapcase(self.str_storage)
        return self if changed else space.w_nil

    @classdef.method("upcase!")
    @check_frozen()
    def method_upcase_i(self, space):
        self.strategy.to_mutable(space, self)
        changed = self.strategy.upcase(self.str_storage)
        return self if changed else space.w_nil

    @classdef.method("downcase!")
    @check_frozen()
    def method_downcase_i(self, space):
        self.strategy.to_mutable(space, self)
        changed = self.strategy.downcase(self.str_storage)
        return self if changed else space.w_nil

    @classdef.method("capitalize!")
    @check_frozen()
    def method_capitalize_i(self, space):
        self.strategy.to_mutable(space, self)
        changed = self.strategy.capitalize(self.str_storage)
        return self if changed else space.w_nil

    def _digits(self, s, i, radix):
        number_seen = False
        while i < len(s):
            c = ord(s[i])
            if c == ord("_") and number_seen:
                i += 1
                continue
            if ord("a") <= c <= ord("z"):
                digit = c - ord("a") + 10
            elif ord("A") <= c <= ord("Z"):
                digit = c - ord("A") + 10
            elif ord("0") <= c <= ord("9"):
                digit = c - ord("0")
            else:
                break
            if digit >= radix:
                break
            number_seen = True
            yield digit
            i += 1

    def to_int(self, s, neg, i, radix):
        val = 0
        for digit in self._digits(s, i, radix):
            # ovfcheck covers only one operation.
            val = ovfcheck(val * radix)
            val = ovfcheck(val + digit)
        if neg:
            val = -val
        return val

    def to_bigint(self, s, neg, i, radix):
        val = rbigint.fromint(0)
        bigint_radix = rbigint.fromint(radix)
        for digit in self._digits(s, i, radix):
            val = val.mul(bigint_radix).add(rbigint.fromint(digit))
        if neg:
            val = val.neg()
        return val

    @classdef.method("match")
    def method_match(self, space, w_pattern, w_pos=None, block=None):
        from topaz.objects.regexpobject import W_RegexpObject
        if not isinstance(w_pattern, W_RegexpObject):
            w_pattern = space.send(space.getclassfor(W_RegexpObject), "new", [w_pattern])
        args_w = [self]
        if w_pos is not None:
            args_w.append(w_pos)
        w_match = space.send(w_pattern, "match", args_w)
        if block is not None and w_match is not space.w_nil:
            return space.invoke_block(block, [w_match])
        return w_match

    @classdef.method("to_i")
    def method_to_i(self, space, w_radix=None):
        if w_radix is None:
            is_radix = False
            radix = 10
        else:
            is_radix = True
            radix = Coerce.int(space, w_radix)
        s = space.str_w(self)
        neg, i, radix = scan_integer_prefix(s, radix, is_radix)
        if not 2 <= radix <= 36:
            raise space.error(space.w_ArgumentError, "invalid radix %d" % radix)
        try:
            value = self.to_int(s, neg, i, radix)
        except OverflowError:
            value = self.to_bigint(s, neg, i, radix)
            return space.newbigint_fromrbigint(value)
        else:
            return space.newint(value)

    @classdef.method("to_f")
    def method_to_f(self, space):
        value = 0.0
        precision = False
        pointer = 0.1
        negative = False
        exponent = False
        multi = 0
        number = False

        for char in space.str_w(self):
            c = ord(char)
            if ord("0") <= c <= ord("9"):
                if exponent:
                    multi = multi * 10 + c - ord("0")
                elif precision:
                    value = value + pointer * (c - ord("0"))
                    pointer /= 10
                else:
                    value = value * 10 + c - ord("0")

                number = True
            elif c == ord("-"):
                if value != 0.0:
                    break
                negative = not negative
            elif c == ord("+"):
                if value != 0.0:
                    break
                pass
            elif c == ord("."):
                if precision or exponent:
                    break
                precision = True
            elif c == ord("e"):
                if exponent:
                    break
                exponent = True
            elif char.isspace():
                if number:
                    break
            else:
                break

        if exponent:
            value = value * math.pow(10, multi)

        return space.newfloat(value)

    @classdef.method("tr", source="str", replacement="str")
    def method_tr(self, space, source, replacement):
        new_string = self.tr_trans(space, source, replacement, False)
        if new_string is None:
            return self.copy(space)
        return space.newstr_fromchars(new_string)

    @classdef.method("tr!", source="str", replacement="str")
    @check_frozen()
    def method_tr_i(self, space, source, replacement):
        new_string = self.tr_trans(space, source, replacement, False)
        if new_string is None:
            return space.w_nil
        self.replace(space, new_string)
        return self

    @classdef.method("tr_s", source="str", replacement="str")
    def method_tr_s(self, space, source, replacement):
        new_string = self.tr_trans(space, source, replacement, True)
        if new_string is None:
            return self.copy(space)
        return space.newstr_fromchars(new_string)

    @classdef.method("tr_s!", source="str", replacement="str")
    @check_frozen()
    def method_tr_s_i(self, space, source, replacement):
        new_string = self.tr_trans(space, source, replacement, True)
        if new_string is None:
            return space.w_nil
        self.replace(space, new_string)
        return self

    def squeeze_chars(self, space, args_w):
        """String#squeeze: the squeezed characters, or None when nothing
        changes. A run of a byte that is in every given set (any byte,
        with no sets) becomes one byte. Sets are tr sets: ranges, a
        leading ^ for negation, backslash escapes."""
        squeezable = [True] * 256
        for w_set in args_w:
            w_set = space.convert_type(w_set, space.w_string, "to_str")
            chars, negate = expand_tr_set(space, space.str_w(w_set), True)
            present = [negate] * 256
            for c in chars:
                present[ord(c)] = not negate
            for i in range(256):
                if not present[i]:
                    squeezable[i] = False
        string = space.str_w(self)
        new_string = []
        changed = False
        has_last = False
        last = "\0"
        for char in string:
            if has_last and char == last and squeezable[ord(char)]:
                changed = True
                continue
            new_string.append(char)
            has_last = True
            last = char
        return new_string if changed else None

    @classdef.method("squeeze")
    def method_squeeze(self, space, args_w):
        new_string = self.squeeze_chars(space, args_w)
        if new_string is None:
            return self.copy(space)
        return space.newstr_fromchars(new_string)

    @classdef.method("squeeze!")
    @check_frozen()
    def method_squeeze_i(self, space, args_w):
        new_string = self.squeeze_chars(space, args_w)
        if new_string is None:
            return space.w_nil
        self.replace(space, new_string)
        return self

    @classdef.method("=~")
    def method_match_operator(self, space, w_obj):
        if space.is_kind_of(w_obj, space.w_string):
            raise space.error(space.w_TypeError, "type mismatch: String given")
        else:
            return space.send(w_obj, "=~", [self])

    @classdef.method("%")
    def method_mod(self, space, w_arg):
        w_listarg = space.convert_type(
            w_arg, space.w_array, "to_ary", raise_error=False
        )
        if w_listarg is space.w_nil:
            args_w = [w_arg]
        else:
            args_w = space.listview(w_listarg)
        elements_w = StringFormatter(space.str_w(self), args_w).format(space)
        return space.newstr_fromstrs(elements_w)

    @classdef.method("getbyte", pos="int")
    def method_getbyte(self, space, pos):
        if pos >= self.length() or pos < -self.length():
            return space.w_nil
        if pos < 0:
            pos += self.length()
        ch = self.strategy.getitem(self.str_storage, pos)
        return space.newint(ord(ch))

    @classdef.method("setbyte", pos="int", replacement="int")
    @check_frozen()
    def method_setbyte(self, space, pos, replacement):
        if pos >= self.length() or pos < -self.length():
            raise space.error(space.w_IndexError,
                "index %d out of string" % pos
            )
        if pos < 0:
            pos += self.length()
        self.strategy.to_mutable(space, self)
        self.strategy.replaceitem(self.str_storage, pos, chr(replacement))
        return space.newint(replacement)

    @classdef.method("include?", substr="str")
    def method_includep(self, space, substr):
        return space.newbool(substr in space.str_w(self))

    def scan_string(self, space, w_pattern):
        string = space.str_w(self)
        pattern = space.str_w(w_pattern)
        idx = string.find(pattern, 0)
        while idx >= 0:
            w_match = space.newstr_fromstr(string[idx:idx + len(pattern)])
            space.infect(w_match, self)
            space.infect(w_match, w_pattern)
            yield w_match
            if not pattern:
                idx += 1
            else:
                idx += len(pattern)
            idx = string.find(pattern, idx)

    def scan_regexp(self, space, w_pattern):
        string = space.str_w(self)
        ctx = w_pattern.make_ctx(string)
        search_from = 0
        while search_from <= len(string):
            ctx.reset(search_from)
            if not self.search_context(space, w_pattern, ctx):
                break
            w_matchdata = w_pattern.get_match_result(space, ctx, string, found=True)
            assert isinstance(w_matchdata, W_MatchDataObject)
            start, end = ctx.match_start, ctx.match_end
            if w_matchdata.size() > 1:
                matches_w = []
                for num in xrange(1, w_matchdata.size(), 1):
                    begin, stop = w_matchdata.get_span(num)
                    if begin < 0 or stop < 0:
                        matches_w.append(space.w_nil)
                        continue
                    w_str = space.newstr_fromstr(string[begin:stop])
                    space.infect(w_str, self)
                    space.infect(w_str, w_pattern)
                    matches_w.append(w_str)
                w_match = space.newarray(matches_w)
            else:
                assert start >= 0 and end >= start
                w_match = space.newstr_fromstr(string[start:end])
                space.infect(w_match, self)
                space.infect(w_match, w_pattern)

            yield w_match

            if start == end:
                search_from = end + utf8_char_length(string, end)
            else:
                search_from = end

    def scan_process_result(self, space, w_match, results_w, block):
        if block:
            space.invoke_block(block, [w_match])
        else:
            results_w.append(w_match)

    @classdef.method("scan")
    def method_scan(self, space, w_pattern, block):
        results_w = []
        w_str_pattern = space.convert_type(w_pattern, space.w_string, "to_str", raise_error=False)
        if w_str_pattern is not space.w_nil:
            for w_match in self.scan_string(space, w_str_pattern):
                self.scan_process_result(space, w_match, results_w, block)
        elif space.is_kind_of(w_pattern, space.w_regexp):
            for w_match in self.scan_regexp(space, w_pattern):
                self.scan_process_result(space, w_match, results_w, block)
        else:
            raise space.error(
                space.w_TypeError,
                "wrong argument type %s (expected Regexp)" % (
                    space.obj_to_s(space.getclass(w_pattern))
                )
            )
        if block:
            return self
        else:
            return space.newarray(results_w)

    @classdef.method("gsub")
    def method_gsub(self, space, w_pattern, w_replacement=None, block=None):
        return self.gsub_main(space, w_pattern, w_replacement, block, first_only=False)

    @classdef.method("sub")
    def method_sub(self, space, w_pattern, w_replacement=None, block=None):
        if w_replacement is None and block is None:
            raise space.error(space.w_ArgumentError, "wrong number of arguments")
        return self.gsub_main(space, w_pattern, w_replacement, block, first_only=True)

    # gsub! and sub! are here, not in Ruby, so that the block and the
    # caller see the matches in $~.
    @classdef.method("gsub!")
    @check_frozen()
    def method_gsub_bang(self, space, w_pattern, w_replacement=None, block=None):
        w_result = self.gsub_main(space, w_pattern, w_replacement, block, first_only=False)
        return self._replace_if_changed(space, w_result)

    @classdef.method("sub!")
    @check_frozen()
    def method_sub_bang(self, space, w_pattern, w_replacement=None, block=None):
        if w_replacement is None and block is None:
            raise space.error(space.w_ArgumentError, "wrong number of arguments")
        w_result = self.gsub_main(space, w_pattern, w_replacement, block, first_only=True)
        return self._replace_if_changed(space, w_result)

    def _replace_if_changed(self, space, w_result):
        assert isinstance(w_result, W_StringObject)
        if space.str_w(w_result) == space.str_w(self):
            return space.w_nil
        self.strategy = w_result.strategy
        self.str_storage = w_result.strategy.copy(w_result.str_storage)
        return self

    def gsub_main(self, space, w_pattern, w_replacement, block, first_only):
        if w_replacement is None and block is None:
            raise space.error(
                space.w_NotImplementedError,
                "gsub enumerator"
            )

        w_hash = None
        replacement = None
        if w_replacement:
            w_hash = space.convert_type(w_replacement, space.w_hash, "to_hash", raise_error=False)
            if w_hash is space.w_nil:
                w_hash = None
                replacement = space.str_w(
                    space.convert_type(w_replacement, space.w_string, "to_str")
                )

        if space.is_kind_of(w_pattern, space.w_regexp):
            return self.gsub_regexp(space, w_pattern, replacement, w_hash, block, first_only)
        elif space.is_kind_of(w_pattern, space.w_string):
            return self.gsub_string(space, w_pattern, replacement, w_hash, block, first_only)
        else:
            raise space.error(
                space.w_TypeError,
                "wrong argument type %s (expected Regexp)" % (
                    space.obj_to_s(space.getclass(w_replacement))
                )
            )

    def gsub_regexp(self, space, w_pattern, replacement, w_hash, block, first_only):
        result = []
        pos = 0
        string = space.str_w(self)
        ctx = w_pattern.make_ctx(string)
        w_lastmatch = space.w_nil
        search_from = 0
        while search_from <= len(string):
            ctx.reset(search_from)
            if not self.search_context(space, w_pattern, ctx):
                break
            start, end = ctx.match_start, ctx.match_end
            assert 0 <= start <= end
            # Sets $~, which a block may read (as $1 and so on).
            w_matchdata = w_pattern.get_match_result(space, ctx, string, found=True)
            assert isinstance(w_matchdata, W_MatchDataObject)
            w_lastmatch = w_matchdata
            result += string[pos:start]
            if replacement is not None:
                if "\\" in replacement:
                    self.gsub_expand_replacement(space, result, replacement, w_matchdata)
                else:
                    result += replacement
            elif block:
                result += self.gsub_regexp_block(space, block, w_matchdata)
            elif w_hash:
                result += self.gsub_regexp_hash(space, w_hash, w_matchdata)
            pos = end
            if start == end:
                # After an empty match, copy one character and search on.
                n = utf8_char_length(string, end)
                if end < len(string):
                    result += string[end:end + n]
                    pos = end + n
                search_from = end + n
            else:
                search_from = end
            if first_only:
                break
        result += string[pos:]
        space.globals.set(space, "$~", w_lastmatch)
        return space.newstr_fromchars(result)

    def gsub_expand_replacement(self, space, result, replacement, w_match):
        """Appends `replacement` to `result` with its backslash sequences
        expanded: \0 to \9, \&, \`, \', \k<name> and \\."""
        assert isinstance(w_match, W_MatchDataObject)
        string = w_match.string
        i = 0
        n = len(replacement)
        while i < n:
            ch = replacement[i]
            if ch != "\\" or i + 1 >= n:
                result.append(ch)
                i += 1
                continue
            nxt = replacement[i + 1]
            i += 2
            start = -1
            end = -1
            if "0" <= nxt <= "9" or nxt == "&":
                group = 0 if nxt == "&" else ord(nxt) - ord("0")
                if group == 0:
                    start, end = w_match.match_start, w_match.match_end
                elif group < w_match.size():
                    start, end = w_match.get_span(group)
            elif nxt == "`":
                start, end = 0, w_match.match_start
            elif nxt == "'":
                start, end = w_match.match_end, len(string)
            elif nxt == "\\":
                result.append("\\")
                continue
            elif nxt == "k" and i < n and replacement[i] == "<":
                close = replacement.find(">", i)
                if close < 0:
                    result.append("\\")
                    result.append("k")
                    continue
                name = replacement[i + 1:close]
                i = close + 1
                if name in w_match.regexp.groupindex:
                    group = w_match.regexp.groupindex[name]
                    if group < w_match.size():
                        start, end = w_match.get_span(group)
                else:
                    raise space.error(space.w_IndexError,
                        "undefined group name reference: %s" % name)
            else:
                result.append("\\")
                result.append(nxt)
                continue
            if 0 <= start <= end:
                result += string[start:end]

    def gsub_regexp_block(self, space, block, w_match):
        w_arg = space.send(w_match, "[]", [space.newint(0)])
        return self.gsub_yield_block(space, block, w_arg)

    def gsub_regexp_hash(self, space, w_hash, w_match):
        w_arg = space.send(w_match, "[]", [space.newint(0)])
        return self.gsub_lookup_hash(space, w_hash, w_arg)

    def gsub_string(self, space, w_pattern, replacement, w_hash, block, first_only):
        result = []
        pos = 0
        string = space.str_w(self)
        pattern = space.str_w(w_pattern)
        search_from = 0
        while search_from <= len(string):
            idx = string.find(pattern, search_from)
            if idx < 0:
                break
            result += string[pos:idx]
            if replacement is not None:
                result += replacement
            elif block:
                result += self.gsub_yield_block(space, block, w_pattern)
            elif w_hash:
                result += self.gsub_lookup_hash(space, w_hash, w_pattern)
            end = idx + len(pattern)
            pos = end
            if not pattern:
                n = utf8_char_length(string, end)
                if end < len(string):
                    result += string[end:end + n]
                    pos = end + n
                search_from = end + n
            else:
                search_from = end
            if first_only:
                break
        result += string[pos:]
        return space.newstr_fromchars(result)

    def gsub_yield_block(self, space, block, w_matchstr):
        w_value = space.invoke_block(block, [w_matchstr])
        return self.gsub_replacement_to_s(space, w_value)

    def gsub_lookup_hash(self, space, w_hash, w_matchstr):
        w_value = space.send(w_hash, "[]", [w_matchstr])
        return self.gsub_replacement_to_s(space, w_value)

    def gsub_replacement_to_s(self, space, w_replacement):
        if space.is_kind_of(w_replacement, space.w_string):
            return space.str_w(w_replacement)
        else:
            w_replacement = space.send(w_replacement, "to_s")
            if space.is_kind_of(w_replacement, space.w_string):
                return space.str_w(w_replacement)
            else:
                return space.any_to_s(w_replacement)

    @classdef.method("chomp!")
    @check_frozen()
    def method_chomp_i(self, space, w_newline=None):
        if w_newline is None:
            w_newline = space.globals.get(space, "$/")
        if w_newline is space.w_nil:
            return space.w_nil
        newline = space.str_w(space.convert_type(w_newline, space.w_string, "to_str"))
        if newline and newline in "\n\r":
            newline = None
        self.strategy.to_mutable(space, self)
        changed = self.strategy.chomp(self.str_storage, newline)
        return self if changed else space.w_nil

    @classdef.method("chop!")
    @check_frozen()
    def method_chop_i(self, space):
        self.strategy.to_mutable(space, self)
        changed = self.strategy.chop(self.str_storage)
        return self if changed else space.w_nil

    @classdef.method("reverse!")
    @check_frozen()
    def method_reverse_i(self, space):
        self.strategy.to_mutable(space, self)
        self.strategy.reverse(self.str_storage)
        return self

    @classdef.method("next!")
    @classdef.method("succ!")
    @check_frozen()
    def method_succ_i(self, space):
        self.strategy.to_mutable(space, self)
        self.strategy.succ(self.str_storage)
        return self

    @classdef.method("insert", index="int", other="str")
    @check_frozen()
    def method_insert(self, space, index, other):
        if index < 0:
            index += self.length() + 1
        if not 0 <= index <= self.length():
            raise space.error(space.w_IndexError,
                "index %d out of string" % index
            )
        self.strategy.to_mutable(space, self)
        self.strategy.insert(self.str_storage, index, other)
        return self

    @classdef.method("prepend", other="str")
    @check_frozen()
    def method_prepend(self, space, other):
        self.strategy.to_mutable(space, self)
        self.strategy.insert(self.str_storage, 0, other)
        return self

    @classdef.method("strip!")
    @check_frozen()
    def method_strip_i(self, space):
        self.strategy.to_mutable(space, self)
        changed = self.strategy.strip(self.str_storage)
        if changed:
            return self
        else:
            return space.w_nil
