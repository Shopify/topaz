import sys

from rpython.rlib.listsort import make_timsort_class
from rpython.rlib.objectmodel import specialize
from rpython.rlib.rstring import StringBuilder
from rpython.rlib.rsre.rsre_constants import (
    OPCODE_LITERAL, OPCODE_LITERAL_IGNORE, OPCODE_SUCCESS, OPCODE_ASSERT,
    OPCODE_MARK, OPCODE_REPEAT, OPCODE_ANY, OPCODE_ANY_ALL, OPCODE_MAX_UNTIL,
    OPCODE_MIN_UNTIL, OPCODE_GROUPREF, OPCODE_AT, OPCODE_BRANCH, OPCODE_RANGE,
    OPCODE_JUMP, OPCODE_ASSERT_NOT, OPCODE_CATEGORY, OPCODE_FAILURE, OPCODE_IN,
    OPCODE_NEGATE, OPCODE_GROUPREF_EXISTS, OPCODE_GROUPREF_IGNORE,
    OPCODE_IN_IGNORE, OPCODE_NOT_LITERAL, OPCODE_NOT_LITERAL_IGNORE
)
from rpython.rlib.rsre.rsre_constants import (
    AT_BEGINNING, AT_BEGINNING_LINE, AT_BEGINNING_STRING, AT_BOUNDARY,
    AT_NON_BOUNDARY, AT_END_LINE, AT_END_STRING,
)
from rpython.rlib.rsre.rsre_char import MAXREPEAT as MAX_REPEAT
from rpython.rlib.rsre.rsre_core import CompiledPattern


IGNORE_CASE = 1 << 0
EXTENDED = 1 << 1
DOT_ALL = 1 << 2
ONCE = 1 << 3

FIXED_ENCODING = 1 << 4
NO_ENCODING = 1 << 5

OPTIONS_MAP = {
    "i": IGNORE_CASE,
    "x": EXTENDED,
    "m": DOT_ALL,
    "o": ONCE,
    "u": FIXED_ENCODING,
    "n": NO_ENCODING,
    "e": FIXED_ENCODING,
    "s": FIXED_ENCODING,
}

FLAGS_MAP = [
    ("m", DOT_ALL),
    ("i", IGNORE_CASE),
    ("x", EXTENDED),
]

SPECIAL_CHARS = "()|?*+{^$.[\\#"

CHARACTER_ESCAPES = {
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
}

CATEGORY_DIGIT = 0
CATEGORY_NOT_DIGIT = 1
CATEGORY_SPACE = 2
CATEGORY_NOT_SPACE = 3
CATEGORY_WORD = 4
CATEGORY_NOT_WORD = 5
CATEGORY_LINEBREAK = 6
CATEGORY_NOT_LINEBREAK = 7
CATEGORY_LOC_WORD = 8
CATEGORY_LOC_NOT_WORD = 9
CATEGORY_UNI_DIGIT = 10
CATEGORY_UNI_NOT_DIGIT = 11
CATEGORY_UNI_SPACE = 12
CATEGORY_UNI_NOT_SPACE = 13
CATEGORY_UNI_WORD = 14
CATEGORY_UNI_NOT_WORD = 15
CATEGORY_UNI_LINEBREAK = 16
CATEGORY_UNI_NOT_LINEBREAK = 17


class UnscopedFlagSet(Exception):
    def __init__(self, global_flags):
        Exception.__init__(self)
        self.global_flags = global_flags


class RegexpError(Exception):
    pass


class ParseError(Exception):
    pass


class Source(object):
    def __init__(self, s):
        self.pos = 0
        self.s = s

        self.ignore_space = False

    def at_end(self):
        s = self.s
        pos = self.pos

        if self.ignore_space:
            while True:
                if pos >= len(s):
                    break
                elif s[pos].isspace():
                    pos += 1
                elif s[pos] == "#":
                    pos = s.find("\n", pos)
                    if pos < 0:
                        pos = len(s)
                else:
                    break
        return pos >= len(s)

    def get(self):
        s = self.s
        pos = self.pos
        if self.ignore_space:
            while True:
                if pos >= len(s):
                    return ""
                elif s[pos].isspace():
                    pos += 1
                elif s[pos] == "#":
                    pos = s.find("\n", pos)
                    if pos < 0:
                        pos = len(s)
                else:
                    break
        try:
            ch = s[pos]
            self.pos = pos + 1
            return ch
        except IndexError:
            self.pos = pos
            return ""
        except ValueError:
            self.pos = len(s)
            return ""

    def match(self, substr):
        s = self.s
        pos = self.pos

        if self.ignore_space:
            for c in substr:
                while True:
                    if pos >= len(s):
                        return False
                    elif s[pos].isspace():
                        pos += 1
                    elif s[pos] == "#":
                        pos = s.find("\n", pos)
                        if pos < 0:
                            pos = len(s)
                    else:
                        break

                if s[pos] != c:
                    return False
                pos += 1
            self.pos = pos
            return True
        else:
            if pos + len(substr) <= len(s):
                matches = True
                for i in xrange(len(substr)):
                    if s[pos + i] != substr[i]:
                        matches = False
            else:
                matches = False
            if not matches:
                return False
            self.pos = pos + len(substr)
            return True

    def expect(self, substr):
        if not self.match(substr):
            raise RegexpError("Missing %s" % substr)


class Info(object):
    OPEN = 0
    CLOSED = 1

    def __init__(self, flags):
        self.flags = flags

        self.group_count = 0
        self.used_groups = {}
        self.group_state = {}
        self.group_index = {}
        self.group_name = {}
        self.named_lists_used = {}
        self.defined_groups = {}

        self.group_offsets = []
        # For subexpression calls (\g<name>): where each group's pattern is
        # in the source, and whether a call is being parsed (then groups do
        # not capture).
        self.group_spans = {}
        self.calling = 0
        # Groups made for atomic groups and possessive quantifiers, which
        # Ruby code does not see.
        self.hidden_groups = {}

    def new_group(self, name=None):
        if name in self.group_index:
            group = self.group_index[name]
        else:
            while True:
                self.group_count += 1
                if name is None or self.group_count not in self.group_name:
                    break
            group = self.group_count
            if name is not None:
                self.group_index[name] = group
                self.group_name[group] = name
        self.used_groups[group] = None
        self.group_state[group] = self.OPEN
        return group

    def close_group(self, group, hidden=False):
        if hidden:
            self.hidden_groups[group] = None
        self.group_state[group] = self.CLOSED

    def normalize_group(self, name):
        if name.isdigit():
            return int(name)
        else:
            return self.group_index[name]

    def is_open_group(self, name):
        group = self.normalize_group(name)
        return group in self.group_state and self.group_state[group] == self.OPEN


BaseSorter = make_timsort_class()


class BranchSorter(BaseSorter):
    def __init__(self, items, order):
        BaseSorter.__init__(self, items)
        self.order = order

    def lt(self, a, b):
        return self.order[a[0]] < self.order[b[0]]


class CompilerContext(object):
    def __init__(self):
        self.data = []

    def emit(self, opcode):
        self.data.append(opcode)

    def tell(self):
        return len(self.data)

    def patch(self, pos, value):
        self.data[pos] = value

    def build(self):
        return self.data[:]


class Counts(object):
    def __init__(self, min_count, max_count=MAX_REPEAT, limited_quantifier=False):
        self.min_count = min_count
        self.max_count = max_count
        self.limited_quantifier = limited_quantifier


class RegexpBase(object):
    _attrs_ = ["positive", "case_insensitive", "zerowidth"]

    def __init__(self, positive=True, case_insensitive=False, zerowidth=False):
        self.positive = positive
        self.case_insensitive = case_insensitive
        self.zerowidth = zerowidth

    def can_be_affix(self):
        # Whether this node may be moved into a common prefix or suffix of
        # the branches of an alternation. Saying no is always safe.
        return False

    def is_empty(self):
        # Whether this node only ever matches the empty string. Every node
        # needs an answer: a missing one crashes the translated
        # interpreter when the node is repeated.
        return False

    def compile_folded(self, ctx):
        # Compiles this node as a member of a case-insensitive set.
        self.compile(ctx)

    @specialize.argtype(1, 2, 3)
    def with_flags(self, positive=None, case_insensitive=None, zerowidth=None):
        positive = positive if positive is not None else self.positive
        case_insensitive = case_insensitive if case_insensitive is not None else self.case_insensitive
        zerowidth = zerowidth if zerowidth is not None else self.zerowidth
        if (positive == self.positive and
            case_insensitive == self.case_insensitive and
                zerowidth == self.zerowidth):
            return self
        return self.rebuild(positive, case_insensitive, zerowidth)


class Character(RegexpBase):
    def __init__(self, value, case_insensitive=False, positive=True, zerowidth=False):
        RegexpBase.__init__(self, case_insensitive=case_insensitive, positive=positive, zerowidth=zerowidth)
        self.value = value

    def rebuild(self, positive, case_insensitive, zerowidth):
        return Character(self.value, positive=positive, case_insensitive=case_insensitive, zerowidth=zerowidth)

    def getwidth(self):
        return 1, 1

    def fix_groups(self):
        pass

    def optimize(self, info, in_set=False):
        return self

    def can_be_affix(self):
        return True

    def is_empty(self):
        return False

    def compile(self, ctx):
        # A negated character is what [^x] optimizes to.
        if self.case_insensitive:
            # The matcher lowercases the subject before comparing.
            ctx.emit(OPCODE_LITERAL_IGNORE if self.positive else OPCODE_NOT_LITERAL_IGNORE)
            ctx.emit(_lower_ascii(self.value))
        else:
            ctx.emit(OPCODE_LITERAL if self.positive else OPCODE_NOT_LITERAL)
            ctx.emit(self.value)

    def compile_folded(self, ctx):
        # As a member of a case-insensitive set.
        ctx.emit(OPCODE_LITERAL)
        ctx.emit(_lower_ascii(self.value))


class Any(RegexpBase):
    def getwidth(self):
        return 1, 1

    def is_empty(self):
        return False

    def fix_groups(self):
        pass

    def optimize(self, info, in_set=False):
        return self

    def compile(self, ctx):
        ctx.emit(OPCODE_ANY)


class AnyAll(RegexpBase):
    def getwidth(self):
        return 1, 1

    def is_empty(self):
        return False

    def fix_groups(self):
        pass

    def optimize(self, info, in_set=False):
        return self

    def compile(self, ctx):
        ctx.emit(OPCODE_ANY_ALL)


class ZeroWidthBase(RegexpBase):
    def getwidth(self):
        return 0, 0

    def is_empty(self):
        return True

    def fix_groups(self):
        pass

    def optimize(self, info, in_set=False):
        return self


class AtPosition(ZeroWidthBase):
    def __init__(self, code):
        ZeroWidthBase.__init__(self)
        self.code = code

    def can_be_affix(self):
        return True

    def compile(self, ctx):
        ctx.emit(OPCODE_AT)
        ctx.emit(self.code)


class Property(RegexpBase):
    def __init__(self, value, positive=True, case_insensitive=False, zerowidth=False):
        RegexpBase.__init__(self, positive=positive, case_insensitive=case_insensitive, zerowidth=zerowidth)
        self.value = value

    def rebuild(self, positive, case_insensitive, zerowidth):
        return Property(self.value, positive, case_insensitive, zerowidth)

    def getwidth(self):
        return 1, 1

    def is_empty(self):
        return False

    def fix_groups(self):
        pass

    def optimize(self, info, in_set=False):
        return self

    def can_be_affix(self):
        return True

    def compile(self, ctx):
        ctx.emit(OPCODE_CATEGORY)
        # Each CATEGORY_NOT_* code is its positive category's code plus one.
        ctx.emit(self.value if self.positive else self.value ^ 1)


class CodePoint(RegexpBase):
    """A \\u escape beyond ASCII in a set, while the set is parsed."""
    def __init__(self, value):
        RegexpBase.__init__(self)
        self.value = value


class WideRange(RegexpBase):
    """Set members from lower to upper, some beyond ASCII, while the set
    is parsed."""
    def __init__(self, lower, upper):
        RegexpBase.__init__(self)
        self.lower = lower
        self.upper = upper


class Range(RegexpBase):
    def __init__(self, lower, upper, positive=True, case_insensitive=False, zerowidth=False):
        RegexpBase.__init__(self, positive=positive, case_insensitive=case_insensitive, zerowidth=zerowidth)
        self.lower = lower
        self.upper = upper

    def getwidth(self):
        return 1, 1

    def rebuild(self, positive, case_insensitive, zerowidth):
        return Range(self.lower, self.upper, positive, case_insensitive, zerowidth)

    def fix_groups(self):
        pass

    def optimize(self, info, in_set=False):
        return self

    def can_be_affix(self):
        return True

    def compile(self, ctx):
        if not self.positive:
            ctx.emit(OPCODE_NEGATE)
        ctx.emit(OPCODE_RANGE)
        ctx.emit(self.lower)
        ctx.emit(self.upper)

    def compile_folded(self, ctx):
        # As a member of a case-insensitive set: the subject is lowercased
        # before it is checked, so add the lowercase of any uppercase part.
        self.compile(ctx)
        lo = max(self.lower, ord("A"))
        hi = min(self.upper, ord("Z"))
        if self.positive and lo <= hi:
            ctx.emit(OPCODE_RANGE)
            ctx.emit(lo + 32)
            ctx.emit(hi + 32)


class Sequence(RegexpBase):
    def __init__(self, items):
        RegexpBase.__init__(self)
        self.items = items

    def getwidth(self):
        lo, hi = 0, 0
        for item in self.items:
            itemlo, itemhi = item.getwidth()
            lo += itemlo
            hi += itemhi
        return lo, hi

    def is_empty(self):
        for item in self.items:
            if not item.is_empty():
                return False
        return True

    def fix_groups(self):
        for item in self.items:
            item.fix_groups()

    def optimize(self, info, in_set=False):
        items = []
        for item in self.items:
            item = item.optimize(info)
            if isinstance(item, Sequence):
                items.extend(item.items)
            else:
                items.append(item)
        return make_sequence(items)

    def compile(self, ctx):
        for item in self.items:
            item.compile(ctx)


def _lower_ascii(value):
    if ord("A") <= value <= ord("Z"):
        return value + 32
    return value


def _same_item(a, b):
    """Whether two parsed items match the same thing. Only literal
    characters are compared; anything else is only the same as itself."""
    if a is b:
        return True
    if isinstance(a, Character) and isinstance(b, Character):
        return (a.value == b.value and a.positive == b.positive and
                a.case_insensitive == b.case_insensitive and
                a.zerowidth == b.zerowidth)
    return False


def _all_items_equal(alternatives, pos, item):
    for a in alternatives:
        if not _same_item(a[pos], item):
            return False
    return True


class Branch(RegexpBase):
    def __init__(self, branches):
        RegexpBase.__init__(self)
        self.branches = branches

    def getwidth(self):
        lo, hi = MAX_REPEAT, 0
        for branch in self.branches:
            branchlo, branchhi = branch.getwidth()
            lo = min(lo, branchlo)
            hi = max(hi, branchhi)
        return lo, hi

    def fix_groups(self):
        for b in self.branches:
            b.fix_groups()

    def is_empty(self):
        for b in self.branches:
            if not b.is_empty():
                return False
        return True

    def _flatten_branches(self, info, branches):
        new_branches = []
        for b in branches:
            b = b.optimize(info)
            if isinstance(b, Branch):
                new_branches.extend(b.branches)
            else:
                new_branches.append(b)
        return new_branches

    def _split_common_prefix(self, info, branches):
        alternatives = []
        for b in branches:
            if isinstance(b, Sequence):
                alternatives.append(b.items)
            else:
                alternatives.append([b])
        max_count = sys.maxint
        for a in alternatives:
            max_count = min(max_count, len(a))
        prefix = alternatives[0]
        pos = 0
        end_pos = max_count
        while (
            pos < end_pos and prefix[pos].can_be_affix() and
            _all_items_equal(alternatives, pos, prefix[pos])
        ):
            pos += 1
        if pos == 0:
            return [], branches
        new_branches = []
        for a in alternatives:
            new_branches.append(make_sequence(a[pos:]))
        return prefix[:pos], new_branches

    def _split_common_suffix(self, info, branches):
        alternatives = []
        for b in branches:
            if isinstance(b, Sequence):
                alternatives.append(b.items)
            else:
                alternatives.append([b])
        max_count = sys.maxint
        for a in alternatives:
            max_count = min(max_count, len(a))
        suffix = alternatives[0]
        pos = -1
        end_pos = -1 - max_count
        while (
            pos > end_pos and suffix[pos].can_be_affix() and
            _all_items_equal(alternatives, pos, suffix[pos])
        ):
            pos -= 1
        count = -1 - pos
        if count == 0:
            return [], branches
        new_branches = []
        for a in alternatives:
            end = len(a) - count
            assert end >= 0
            new_branches.append(make_sequence(a[:end]))
        start = len(suffix) - count
        assert start >= 0
        return suffix[start:], new_branches

    def _is_simple_character(self, c):
        return isinstance(c, Character) and c.positive and not c.case_insensitive

    def _flush_char_prefix(self, info, prefixed, order, new_branches):
        if not prefixed:
            return
        items = prefixed.items()
        sorter = BranchSorter(items, order)
        sorter.sort()
        for value, branches in items:
            if len(branches) == 1:
                new_branches.append(make_sequence(branches[0]))
            else:
                subbranches = []
                optional = False
                for b in branches:
                    if len(b) > 1:
                        subbranches.append(make_sequence(b[1:]))
                    elif not optional:
                        subbranches.append(Sequence([]))
                        optional = True
                sequence = Sequence([Character(value), Branch(subbranches)])
                new_branches.append(sequence.optimize(info))
        prefixed.clear()
        order.clear()

    def _merge_common_prefixes(self, info, branches):
        prefixed = {}
        order = {}
        new_branches = []
        for b in branches:
            if self._is_simple_character(b):
                assert isinstance(b, Character)
                prefixed.setdefault(b.value, []).append([b])
                order.setdefault(b.value, len(order))
            elif isinstance(b, Sequence) and b.items and self._is_simple_character(b.items[0]):
                item = b.items[0]
                assert isinstance(item, Character)
                prefixed.setdefault(item.value, []).append(b.items)
                order.setdefault(item.value, len(order))
            else:
                self._flush_char_prefix(info, prefixed, order, new_branches)
                new_branches.append(b)
        self._flush_char_prefix(info, prefixed, order, new_branches)
        return new_branches

    def _flush_set_members(self, info, items, case_insensitive, new_branches):
        if not items:
            return
        if len(items) == 1:
            [item] = items.keys()
        else:
            item = SetUnion(info, items.keys()).optimize(info)
        new_branches.append(item.with_flags(case_insensitive=case_insensitive))
        items.clear()

    def _reduce_to_set(self, info, branches):
        new_branches = []
        items = {}
        case_insensitive = False
        for b in branches:
            # Only positive single characters and classes can become members
            # of one set: a set member cannot be negated on its own.
            if ((isinstance(b, Character) and b.positive) or
                    isinstance(b, Property)):
                if b.case_insensitive != case_insensitive:
                    self._flush_set_members(info, items, case_insensitive, new_branches)
                    case_insensitive = b.case_insensitive
                items[b.with_flags(case_insensitive=False)] = False
            else:
                self._flush_set_members(info, items, case_insensitive, new_branches)
                new_branches.append(b)
        self._flush_set_members(info, items, case_insensitive, new_branches)
        return new_branches

    def optimize(self, info, in_set=False):
        branches = self._flatten_branches(info, self.branches)

        prefix, branches = self._split_common_prefix(info, branches)
        suffix, branches = self._split_common_suffix(info, branches)

        branches = self._merge_common_prefixes(info, branches)
        branches = self._reduce_to_set(info, branches)
        if len(branches) > 1:
            sequence = prefix + [Branch(branches)] + suffix
        else:
            sequence = prefix + branches + suffix
        return make_sequence(sequence)

    def compile(self, ctx):
        ctx.emit(OPCODE_BRANCH)
        tail = []
        for b in self.branches:
            pos = ctx.tell()
            ctx.emit(0)
            b.compile(ctx)
            ctx.emit(OPCODE_JUMP)
            tail.append(ctx.tell())
            ctx.emit(0)
            ctx.patch(pos, ctx.tell() - pos)
        ctx.emit(0)
        for t in tail:
            ctx.patch(t, ctx.tell() - t)


class BaseRepeat(RegexpBase):
    def __init__(self, subpattern, min_count, max_count):
        RegexpBase.__init__(self)
        self.subpattern = subpattern
        self.min_count = min_count
        self.max_count = max_count

    def getwidth(self):
        lo, hi = self.subpattern.getwidth()
        lo = min(lo * self.min_count, MAX_REPEAT)
        if self.max_count >= MAX_REPEAT:
            hi = MAX_REPEAT
        else:
            hi = min(hi * self.max_count, MAX_REPEAT)
        return lo, hi

    def fix_groups(self):
        self.subpattern.fix_groups()

    def is_empty(self):
        return self.subpattern.is_empty()

    def compile(self, ctx):
        ctx.emit(OPCODE_REPEAT)
        pos = ctx.tell()
        ctx.emit(0)
        ctx.emit(self.min_count)
        ctx.emit(self.max_count)
        self.subpattern.compile(ctx)
        ctx.patch(pos, ctx.tell() - pos)
        ctx.emit(self.UNTIL_OPCODE)


class GreedyRepeat(BaseRepeat):
    UNTIL_OPCODE = OPCODE_MAX_UNTIL

    def can_be_affix(self):
        return True

    def optimize(self, info, in_set=False):
        subpattern = self.subpattern.optimize(info)
        return GreedyRepeat(subpattern, self.min_count, self.max_count)


class LazyRepeat(BaseRepeat):
    UNTIL_OPCODE = OPCODE_MIN_UNTIL

    def optimize(self, info, in_set=False):
        subpattern = self.subpattern.optimize(info)
        return LazyRepeat(subpattern, self.min_count, self.max_count)


class LookAround(RegexpBase):
    def __init__(self, subpattern, behind, positive):
        RegexpBase.__init__(self, positive=positive)
        self.subpattern = subpattern
        self.behind = behind

    def is_empty(self):
        # Zero-width, whatever it looks at.
        return True

    def getwidth(self):
        return 0, 0

    def fix_groups(self):
        self.subpattern.fix_groups()

    def can_be_affix(self):
        return self.subpattern.can_be_affix()

    def optimize(self, info, in_set=False):
        return LookAround(self.subpattern.optimize(info), self.behind, self.positive)

    def compile(self, ctx):
        ctx.emit(OPCODE_ASSERT if self.positive else OPCODE_ASSERT_NOT)
        pos = ctx.tell()
        ctx.emit(0)
        if self.behind:
            lo, hi = self.subpattern.getwidth()
            if lo != hi:
                raise RegexpError("look-behind requires fixed-width pattern")
            ctx.emit(lo)
        else:
            ctx.emit(0)
        self.subpattern.compile(ctx)
        ctx.emit(OPCODE_SUCCESS)
        ctx.patch(pos, ctx.tell() - pos)


class Group(RegexpBase):
    def __init__(self, info, group, subpattern):
        RegexpBase.__init__(self)
        self.info = info
        self.group = group
        self.subpattern = subpattern

    def getwidth(self):
        return self.subpattern.getwidth()

    def fix_groups(self):
        self.info.defined_groups[self.group] = self
        self.subpattern.fix_groups()

    def can_be_affix(self):
        return False

    def optimize(self, info, in_set=False):
        return Group(self.info, self.group, self.subpattern.optimize(info))

    def is_empty(self):
        return False

    def compile(self, ctx):
        ctx.emit(OPCODE_MARK)
        ctx.emit((self.group - 1) * 2)
        self.subpattern.compile(ctx)
        ctx.emit(OPCODE_MARK)
        ctx.emit((self.group - 1) * 2 + 1)


class GroupExistsBranch(RegexpBase):
    def __init__(self, info, group, codeyes, codeno):
        RegexpBase.__init__(self)
        self.info = info
        self.group = group
        self.codeyes = codeyes
        self.codeno = codeno

    def getwidth(self):
        yeslo, yeshi = self.codeyes.getwidth()
        nolo, nohi = self.codeno.getwidth()
        return min(yeslo, nolo), max(yeshi, nohi)

    def can_be_affix(self):
        return False

    def fix_groups(self):
        if not 1 <= self.group <= self.info.group_count:
            raise RegexpError("unknown group")

    def optimize(self, info, in_set=False):
        return self

    def compile(self, ctx):
        ctx.emit(OPCODE_GROUPREF_EXISTS)
        skipno = ctx.tell()
        ctx.emit(self.group - 1)
        ctx.emit(0)
        self.codeyes.compile(ctx)
        ctx.emit(OPCODE_JUMP)
        skipyes = ctx.tell()
        ctx.emit(0)
        ctx.patch(skipno + 1, ctx.tell() - skipno)
        if self.codeno:
            self.codeno.compile(ctx)
        else:
            ctx.emit(OPCODE_FAILURE)
        ctx.patch(skipyes, ctx.tell() - skipyes)


class RefGroup(RegexpBase):
    def __init__(self, info, group, case_insensitive=False):
        RegexpBase.__init__(self, case_insensitive=case_insensitive)
        self.info = info
        self.group = group

    def getwidth(self):
        return 0, MAX_REPEAT

    def can_be_affix(self):
        return False

    def fix_groups(self):
        if not 1 <= self.group <= self.info.group_count:
            raise RegexpError("unknown group")

    def optimize(self, info, in_set=False):
        return self

    def compile(self, ctx):
        if self.case_insensitive:
            ctx.emit(OPCODE_GROUPREF_IGNORE)
        else:
            ctx.emit(OPCODE_GROUPREF)
        ctx.emit(self.group - 1)


class SetBase(RegexpBase):
    def __init__(self, info, items, positive=True, case_insensitive=False, zerowidth=False):
        RegexpBase.__init__(self, positive=positive, case_insensitive=case_insensitive, zerowidth=zerowidth)
        self.info = info
        self.items = items

    def getwidth(self):
        return 1, 1

    def is_empty(self):
        return False

    def can_be_affix(self):
        return True

    def fix_groups(self):
        pass


class SetUnion(SetBase):
    def optimize(self, info, in_set=False):
        items = []
        for item in self.items:
            item = item.optimize(info, in_set=True)
            if isinstance(item, SetUnion) and item.positive:
                items.extend(item.items)
            else:
                items.append(item)
        if len(items) == 1 and not isinstance(items[0], Range):
            return items[0].with_flags(
                positive=items[0].positive == self.positive,
                case_insensitive=self.case_insensitive,
                zerowidth=self.zerowidth
            ).optimize(info, in_set=in_set)
        return SetUnion(self.info, items, positive=self.positive, case_insensitive=self.case_insensitive, zerowidth=self.zerowidth)

    def rebuild(self, positive, case_insensitive, zerowidth):
        return SetUnion(self.info, self.items, positive, case_insensitive, zerowidth).optimize(self.info)

    def compile(self, ctx):
        ctx.emit(OPCODE_IN_IGNORE if self.case_insensitive else OPCODE_IN)
        pos = ctx.tell()
        ctx.emit(0)
        if not self.positive:
            ctx.emit(OPCODE_NEGATE)
        for item in self.items:
            if self.case_insensitive:
                item.compile_folded(ctx)
            else:
                item.compile(ctx)
        ctx.emit(OPCODE_FAILURE)
        ctx.patch(pos, ctx.tell() - pos)


class SetIntersection(SetBase):
    def rebuild(self, positive, case_insensitive, zerowidth):
        return SetIntersection(self.info, self.items, positive=positive, case_insensitive=case_insensitive, zerowidth=zerowidth)

    def optimize(self, info, in_set=False):
        items = []
        for item in self.items:
            item = item.optimize(info, in_set=True)
            if isinstance(item, SetIntersection) and item.positive:
                items.extend(item.items)
            else:
                items.append(item)
        if len(items) == 1:
            return items[0].with_flags(
                case_insensitive=self.case_insensitive,
                zerowidth=self.zerowidth,
            ).optimize(info, in_set)
        return SetIntersection(info, items)

    def compile(self, ctx):
        Sequence([
            LookAround(item, behind=False, positive=True)
            for item in self.items[:-1]
        ] + [self.items[-1]]).compile(ctx)


POSITION_ESCAPES = {
    "A": AtPosition(AT_BEGINNING_STRING),
    "z": AtPosition(AT_END_STRING),
    "Z": AtPosition(AT_END_STRING),

    "b": AtPosition(AT_BOUNDARY),
    "B": AtPosition(AT_NON_BOUNDARY),
}
CHARSET_ESCAPES = {
    "d": Property(CATEGORY_DIGIT),
    "D": Property(CATEGORY_NOT_DIGIT),
    "w": Property(CATEGORY_WORD),
    "W": Property(CATEGORY_NOT_WORD),
    "s": Property(CATEGORY_SPACE),
    "S": Property(CATEGORY_NOT_SPACE),
}
PROPERTIES = {
    "digit": CATEGORY_DIGIT,
    "space": CATEGORY_SPACE,
}
# Bytes 0x80 and up count as letters, so that the classes match the
# characters of UTF-8 text the way CRuby's Unicode classes do.
EXTRA_POSIX_PROPERTIES = {
    "alnum": [Range(ord("a"), ord("z")), Range(ord("A"), ord("Z")),
              Range(ord("0"), ord("9")), Range(0x80, 0xff)],
    "alpha": [Range(ord("a"), ord("z")), Range(ord("A"), ord("Z")),
              Range(0x80, 0xff)],
    "word": [Range(ord("a"), ord("z")), Range(ord("A"), ord("Z")),
             Range(ord("0"), ord("9")), Character(ord("_")), Range(0x80, 0xff)],
    "graph": [Range(33, 126), Range(0x80, 0xff)],
    "print": [Range(32, 126), Range(0x80, 0xff)],
    "blank": [Character(ord(c)) for c in " \t"],
    "cntrl": [Range(0, 31), Character(127)],
    "punct": [Character(ord(c)) for c in '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'],
    "lower": [Range(ord("a"), ord("z"))],
    "upper": [Range(ord("A"), ord("Z"))],
    "xdigit": [Range(ord("0"), ord("9")), Range(ord("a"), ord("f")), Range(ord("A"), ord("F"))],
}


def make_character(info, value, in_set=False):
    if in_set:
        return Character(value)
    return Character(value, case_insensitive=info.flags & IGNORE_CASE)


def make_sequence(items):
    if len(items) == 1:
        return items[0]
    return Sequence(items)


def make_atomic(info, subpattern):
    group = info.new_group()
    info.close_group(group, hidden=True)
    return Sequence([
        LookAround(Group(info, group, subpattern), behind=False, positive=True),
        RefGroup(info, group),
    ])


def make_ref_group(info, name):
    return RefGroup(info, name, case_insensitive=info.flags & IGNORE_CASE)


def _parse_pattern(source, info):
    previous_groups = info.used_groups.copy()
    branches = [_parse_sequence(source, info)]
    all_groups = info.used_groups
    while source.match("|"):
        info.used_groups = previous_groups.copy()
        branches.append(_parse_sequence(source, info))
        all_groups.update(info.used_groups)
    info.used_groups = all_groups

    if len(branches) == 1:
        return branches[0]
    return Branch(branches)


def _parse_sequence(source, info):
    sequence = []
    item = _parse_item(source, info)
    while item:
        sequence.append(item)
        item = _parse_item(source, info)

    return make_sequence(sequence)


def _parse_item(source, info):
    element = _parse_element(source, info)
    counts = _parse_quantifier(source, info)
    if counts is not None:
        min_count, max_count = counts.min_count, counts.max_count

        if element.is_empty() or min_count == max_count == 1:
            return element

        if source.match("?"):
            return LazyRepeat(element, min_count, max_count)
        elif source.match("+"):
            if counts.limited_quantifier:
                return GreedyRepeat(GreedyRepeat(element, min_count, max_count), 1, MAX_REPEAT)
            else:
                return make_atomic(info, GreedyRepeat(element, min_count, max_count))
        else:
            return GreedyRepeat(element, min_count, max_count)
    return element


def _parse_element(source, info):
    here = source.pos
    ch = source.get()
    if ch in SPECIAL_CHARS:
        if ch in ")|":
            source.pos = here
            return None
        elif ch == "\\":
            return _parse_escape(source, info, in_set=False)
        elif ch == "(":
            element = _parse_paren(source, info)
            if element is not None:
                return element
        elif ch == ".":
            if info.flags & DOT_ALL:
                return AnyAll()
            else:
                return Any()
        elif ch == "[":
            return _parse_set(source, info)
        elif ch == "^":
            return AtPosition(AT_BEGINNING_LINE)
        elif ch == "$":
            return AtPosition(AT_END_LINE)
        elif ch == "{":
            here2 = source.pos
            counts = _parse_quantifier(source, info)
            if counts is not None:
                raise RegexpError("nothing to repeat")
            source.pos = here2
            return make_character(info, ord(ch[0]))
        elif ch in "?*+":
            raise RegexpError("nothing to repeat")
        else:
            return make_character(info, ord(ch[0]))
    else:
        return make_character(info, ord(ch[0]))


def _parse_quantifier(source, info):
    while True:
        here = source.pos
        if source.match("?"):
            return Counts(0, 1)
        elif source.match("*"):
            return Counts(0)
        elif source.match("+"):
            return Counts(1)
        elif source.match("{"):
            try:
                return _parse_limited_quantifier(source)
            except ParseError:
                pass
        elif source.match("(?#"):
            _parse_comment(source)
            continue
        break
    source.pos = here
    return None


def _parse_paren(source, info):
    if source.match("?"):
        # A comment group. In extended mode a bare # would start a comment
        # to the end of the line, so look at the raw text.
        if source.pos < len(source.s) and source.s[source.pos] == "#":
            source.pos += 1
            _parse_comment(source)
            return Sequence([])
        if source.match("<"):
            if source.match("="):
                return _parse_lookaround(source, info, behind=True, positive=True)
            elif source.match("!"):
                return _parse_lookaround(source, info, behind=True, positive=False)
            name = _parse_name(source)
            source.expect(">")
            if info.calling > 0:
                return _parse_called_group_body(source, info)
            group = info.new_group(name)
            return _parse_group_body(source, info, group)
        elif source.match("="):
            return _parse_lookaround(source, info, behind=False, positive=True)
        elif source.match("!"):
            return _parse_lookaround(source, info, behind=False, positive=False)
        elif source.match("#"):
            _parse_comment(source)
            return Sequence([])
        elif source.match(">"):
            return _parse_atomic(source, info)
        elif source.match(":"):
            subpattern = _parse_pattern(source, info)
            source.expect(")")
            return subpattern
        elif source.match("("):
            if source.match("<"):
                groupref = _parse_name(source)
                source.expect(">")
            else:
                groupref = _parse_name(source)
            source.expect(")")
            groupidx = info.normalize_group(groupref)
            subpattern = _parse_pattern(source, info)
            source.expect(")")
            if not isinstance(subpattern, Branch):
                codeyes = subpattern
                codeno = None
            elif len(subpattern.branches) > 2:
                raise RegexpError("invalid conditional pattern")
            else:
                codeyes = subpattern.branches[0]
                codeno = subpattern.branches[1]
            return GroupExistsBranch(info, groupidx, codeyes, codeno)
        here = source.pos
        ch = source.get()
        if ch and ch in "-imx":
            return _parse_flags_group(source, info, ch)
        source.pos = here
        raise RegexpError("undefined group option")
    if info.calling > 0:
        return _parse_called_group_body(source, info)
    group = info.new_group()
    return _parse_group_body(source, info, group)


def _parse_group_body(source, info, group):
    start = source.pos
    saved_flags = info.flags
    saved_ignore = source.ignore_space
    try:
        subpattern = _parse_pattern(source, info)
    finally:
        source.ignore_space = saved_ignore
        info.flags = saved_flags
    info.group_spans[group] = GroupSpan(start, source.pos, saved_flags, saved_ignore)
    source.expect(")")
    info.close_group(group)
    return Group(info, group, subpattern)


def _parse_called_group_body(source, info):
    """A group inside a group being called: matched again, without
    capturing."""
    saved_flags = info.flags
    saved_ignore = source.ignore_space
    try:
        subpattern = _parse_pattern(source, info)
    finally:
        source.ignore_space = saved_ignore
        info.flags = saved_flags
    source.expect(")")
    return subpattern


class GroupSpan(object):
    def __init__(self, start, end, flags, ignore_space):
        self.start = start
        self.end = end
        self.flags = flags
        self.ignore_space = ignore_space


def _parse_subexp_call(source, info):
    """\g<name> or \g<n>: the group's pattern, matched again here (it is
    parsed again from the source). Its captures are not updated."""
    if source.match("<"):
        close = ">"
    elif source.match("'"):
        close = "'"
    else:
        raise RegexpError("invalid group name")
    name = _parse_name(source)
    source.expect(close)
    if name == "0" or not (name.isdigit() or name in info.group_index):
        raise RegexpError("undefined name <%s> reference" % name)
    group = info.normalize_group(name)
    span = info.group_spans.get(group, None)
    if span is None:
        raise RegexpError("recursive or forward subexpression calls are not supported")
    here = source.pos
    saved_flags = info.flags
    saved_ignore = source.ignore_space
    source.pos = span.start
    info.flags = span.flags
    source.ignore_space = span.ignore_space
    info.calling += 1
    try:
        subpattern = _parse_pattern(source, info)
    finally:
        info.calling -= 1
        info.flags = saved_flags
        source.ignore_space = saved_ignore
    if source.pos != span.end:
        raise RegexpError("invalid subexpression call")
    source.pos = here
    return subpattern


def _parse_flags_group(source, info, ch):
    """(?imx-imx) sets flags for the rest of the enclosing group, and
    (?imx-imx:subpattern) for the subpattern. `ch` is the first flag
    character, already read."""
    on = 0
    off = 0
    turning_off = False
    while True:
        if ch == "-":
            if turning_off:
                raise RegexpError("undefined group option")
            turning_off = True
        elif ch == "i" or ch == "m" or ch == "x":
            if ch == "i":
                flag = IGNORE_CASE
            elif ch == "m":
                flag = DOT_ALL
            else:
                flag = EXTENDED
            if turning_off:
                off |= flag
            else:
                on |= flag
        elif ch == ":":
            saved_flags = info.flags
            saved_ignore = source.ignore_space
            info.flags = (info.flags | on) & ~off
            source.ignore_space = bool(info.flags & EXTENDED)
            try:
                subpattern = _parse_pattern(source, info)
                # Still in the group's mode: (?x: a ) may end in spaces.
                source.expect(")")
            finally:
                info.flags = saved_flags
                source.ignore_space = saved_ignore
            return subpattern
        elif ch == ")":
            info.flags = (info.flags | on) & ~off
            source.ignore_space = bool(info.flags & EXTENDED)
            return Sequence([])
        else:
            raise RegexpError("undefined group option")
        ch = source.get()
        if not ch:
            raise RegexpError("end pattern in group")


def _parse_atomic(source, info):
    saved_flags = info.flags
    saved_ignore = source.ignore_space
    try:
        subpattern = _parse_pattern(source, info)
    finally:
        source.ignore_space = saved_ignore
        info.flags = saved_flags
    source.expect(")")
    return make_atomic(info, subpattern)


def _parse_set(source, info):
    saved_ignore = source.ignore_space
    source.ignore_space = False
    negate = source.match("^")
    try:
        item = _parse_set_intersect(source, info)
        source.expect("]")
    finally:
        source.ignore_space = saved_ignore

    wide = []
    if isinstance(item, WideRange):
        wide.append(item)
        item = None
    elif isinstance(item, SetUnion):
        narrow = []
        for member in item.items:
            if isinstance(member, WideRange):
                wide.append(member)
            else:
                narrow.append(member)
        if wide:
            item = SetUnion(info, narrow) if narrow else None
    if wide:
        return _make_wide_set(info, item, wide, negate)
    assert item is not None
    if negate:
        item = item.with_flags(positive=not item.positive)
    return item.with_flags(case_insensitive=info.flags & IGNORE_CASE)


def _make_wide_set(info, narrow, wide, negate):
    """A set with members beyond ASCII, which match as UTF-8 byte
    sequences: the ASCII part stays a set, the rest become alternatives.
    A negated set is a negative lookahead for those before the set."""
    alternatives = []
    for member in wide:
        lower = member.lower
        if lower < 0x80:
            upper = min(member.upper, 0x7f)
            ascii = Range(lower, upper) if lower != upper else Character(lower)
            if narrow is None:
                narrow = SetUnion(info, [ascii])
            else:
                narrow = SetUnion(info, [narrow, ascii])
            lower = 0x80
        if lower > member.upper:
            continue
        for ranges in _utf8_sequences(lower, member.upper):
            items = []
            for byte_lower, byte_upper in ranges:
                if byte_lower == byte_upper:
                    items.append(Character(byte_lower))
                else:
                    items.append(SetUnion(info, [Range(byte_lower, byte_upper)]))
            alternatives.append(Sequence(items))
    if negate:
        # Any one character, ASCII outside the narrow part or a whole UTF-8
        # sequence, that is not one of the alternatives.
        ascii = SetUnion(info, [Range(0, 0x7f)])
        if narrow is not None:
            ascii = SetIntersection(info, [narrow.with_flags(positive=False), ascii])
        continuation = SetUnion(info, [Range(0x80, 0xbf)])
        character = Branch([
            ascii,
            Sequence([SetUnion(info, [Range(0xc0, 0xdf)]), continuation]),
            Sequence([SetUnion(info, [Range(0xe0, 0xef)]), continuation,
                      continuation]),
            Sequence([SetUnion(info, [Range(0xf0, 0xf7)]), continuation,
                      continuation, continuation]),
        ])
        if not alternatives:
            return character
        return Sequence([
            LookAround(Branch(alternatives), behind=False, positive=False),
            character,
        ])
    if narrow is not None:
        alternatives.insert(0, narrow)
    if len(alternatives) == 1:
        return alternatives[0]
    return Branch(alternatives)


def _utf8_encode(value):
    if value < 0x80:
        return [value]
    if value < 0x800:
        return [0xc0 | (value >> 6), 0x80 | (value & 0x3f)]
    if value < 0x10000:
        return [0xe0 | (value >> 12), 0x80 | ((value >> 6) & 0x3f),
                0x80 | (value & 0x3f)]
    return [0xf0 | (value >> 18), 0x80 | ((value >> 12) & 0x3f),
            0x80 | ((value >> 6) & 0x3f), 0x80 | (value & 0x3f)]


def _utf8_sequences(lower, upper):
    """The UTF-8 encodings of lower..upper as a list of byte-range
    sequences, each a list of (lower, upper) byte pairs."""
    result = []
    for low_bound, high_bound in [(0x80, 0x7ff), (0x800, 0xffff),
                                  (0x10000, 0x10ffff)]:
        a = max(lower, low_bound)
        b = min(upper, high_bound)
        if a <= b:
            _utf8_split(a, b, result)
    return result


def _utf8_split(lower, upper, result):
    n = len(_utf8_encode(lower))
    for i in range(1, n):
        mask = (1 << (6 * i)) - 1
        if lower & ~mask != upper & ~mask:
            if lower & mask != 0:
                _utf8_split(lower, lower | mask, result)
                _utf8_split((lower | mask) + 1, upper, result)
                return
            if upper & mask != mask:
                _utf8_split(lower, (upper & ~mask) - 1, result)
                _utf8_split(upper & ~mask, upper, result)
                return
    lower_bytes = _utf8_encode(lower)
    upper_bytes = _utf8_encode(upper)
    ranges = []
    for i in range(len(lower_bytes)):
        ranges.append((lower_bytes[i], upper_bytes[i]))
    result.append(ranges)


def _parse_set_intersect(source, info):
    items = [_parse_set_implicit_union(source, info)]
    while source.match("&&"):
        items.append(_parse_set_implicit_union(source, info))

    if len(items) == 1:
        return items[0]
    return SetIntersection(info, items)


def _parse_set_implicit_union(source, info):
    items = [_parse_set_member(source, info)]
    while True:
        here = source.pos
        if source.match("]") or source.match("&&"):
            source.pos = here
            break
        items.append(_parse_set_member(source, info))
    if len(items) == 1 and not isinstance(items[0], Range):
        return items[0]
    return SetUnion(info, items)


def _parse_set_member(source, info):
    start = _parse_set_item(source, info)
    if isinstance(start, CodePoint):
        here = source.pos
        if source.match("-") and not source.match("]"):
            end = _parse_set_item(source, info)
            if isinstance(end, Character):
                end_value = end.value
            elif isinstance(end, CodePoint):
                end_value = end.value
            else:
                raise RegexpError("bad character range")
            if start.value > end_value:
                raise RegexpError("bad character range")
            return WideRange(start.value, end_value)
        source.pos = here
        return WideRange(start.value, start.value)
    if (not isinstance(start, Character) or not start.positive or
            not source.match("-")):
        return start

    here = source.pos
    if source.match("]"):
        source.pos = here
        return SetUnion(info, [start, Character(ord("-"))])
    end = _parse_set_item(source, info)
    if isinstance(end, CodePoint):
        if start.value > end.value:
            raise RegexpError("bad character range")
        return WideRange(start.value, end.value)
    if not isinstance(end, Character) or not end.positive:
        return SetUnion(info, [start, Character(ord("-")), end])
    if start.value > end.value:
        raise RegexpError("bad character range")
    if start.value == end.value:
        return start
    return Range(start.value, end.value)


def _parse_set_item(source, info):
    if source.match("\\"):
        return _parse_escape(source, info, in_set=True)

    here = source.pos
    if source.match("[:"):
        try:
            return _parse_posix_class(source, info)
        except ParseError:
            source.pos = here
    if source.match("["):
        negate = source.match("^")
        item = _parse_set_intersect(source, info)
        source.expect("]")
        if negate:
            item = item.with_flags(positive=not item.positive)
        return item
    ch = source.get()
    if not ch:
        raise RegexpError("bad set")
    return Character(ord(ch[0]))


def _parse_escape(source, info, in_set):
    saved_ignore = source.ignore_space
    source.ignore_space = False
    ch = source.get()
    source.ignore_space = saved_ignore
    if not ch:
        raise RegexpError("bad escape")
    if ch == "g" and not in_set:
        here = source.pos
        if source.match("<") or source.match("'"):
            source.pos = here
            return _parse_subexp_call(source, info)
        return make_character(info, ord(ch[0]), in_set)
    elif ch == "k" and not in_set:
        here = source.pos
        if source.match("<"):
            source.pos = here
            return _parse_group_ref(source, info)
        return make_character(info, ord(ch[0]), in_set)
    elif ch == "G" and not in_set:
        return AtPosition(AT_BEGINNING)
    elif ch in "pP":
        return _parse_property(source, info, ch == "p", in_set)
    elif ch in "hH":
        # A hexadecimal digit, or not one.
        return SetUnion(info, [
            Range(ord("0"), ord("9")), Range(ord("a"), ord("f")),
            Range(ord("A"), ord("F")),
        ], positive=(ch == "h"))
    elif ch == "x":
        return make_character(info, _parse_hex_digits(source, 2), in_set)
    elif ch == "u":
        if source.match("{"):
            value = _parse_hex_digits(source, 8)
            if not source.match("}"):
                raise RegexpError("invalid Unicode escape")
        else:
            value = _parse_hex_digits(source, 4)
        return _make_code_point(info, value, in_set)
    elif ch == "c" or (ch == "C" and source.match("-")):
        c = source.get()
        if not c:
            raise RegexpError("end pattern at control")
        return make_character(info, ord(c[0]) & 0x1f, in_set)
    elif ch == "e":
        return make_character(info, 0x1b, in_set)
    elif ch.isalpha():
        if not in_set:
            if ch in POSITION_ESCAPES:
                return POSITION_ESCAPES[ch]
        if ch in CHARSET_ESCAPES:
            return CHARSET_ESCAPES[ch]
        elif ch in CHARACTER_ESCAPES:
            return Character(ord(CHARACTER_ESCAPES[ch]))
        return make_character(info, ord(ch[0]), in_set)
    elif ch.isdigit():
        return _parse_numeric_escape(source, info, ch, in_set)
    else:
        return make_character(info, ord(ch[0]), in_set)


def _parse_lookaround(source, info, behind, positive):
    saved_flags = info.flags
    saved_ignore = source.ignore_space
    try:
        subpattern = _parse_pattern(source, info)
    finally:
        source.ignore_space = saved_ignore
        info.flags = saved_flags
    source.expect(")")
    return LookAround(subpattern, behind=behind, positive=positive)


def _parse_limited_quantifier(source):
    min_count = _parse_count(source)
    ch = source.get()
    if ch == ",":
        max_count = _parse_count(source)
        if not source.match("}"):
            raise ParseError
        min_count = int(min_count) if min_count else 0
        max_count = int(max_count) if max_count else MAX_REPEAT
        if min_count > max_count:
            raise RegexpError("min repeat gereater than max repeat")
        if max_count > MAX_REPEAT:
            raise RegexpError("repeat count too big")
        return Counts(min_count, max_count, limited_quantifier=True)
    if ch != "}":
        raise ParseError
    if not min_count:
        raise ParseError
    min_count = int(min_count)
    if min_count > MAX_REPEAT:
        raise RegexpError("repeat count too big")
    return Counts(min_count, min_count, limited_quantifier=True)


def _parse_count(source):
    b = StringBuilder(2)
    while True:
        here = source.pos
        ch = source.get()
        if ch.isdigit():
            b.append(ch)
        else:
            source.pos = here
            break
    return b.build()


def _parse_comment(source):
    while True:
        ch = source.get()
        if ch == ")":
            break
        elif not ch:
            break


def _parse_name(source):
    b = StringBuilder(5)
    while True:
        here = source.pos
        ch = source.get()
        if ch in ")>":
            source.pos = here
            break
        elif not ch:
            break
        else:
            b.append(ch)
    return b.build()


def _parse_plain_flags(source):
    b = StringBuilder(4)
    while True:
        ch = source.get()
        if ch == ":":
            break
        else:
            b.append(ch)
    return b.build()


def _parse_group_ref(source, info):
    source.expect("<")
    name = _parse_name(source)
    source.expect(">")
    if info.is_open_group(name):
        raise RegexpError("can't refer to an open group")
    return make_ref_group(info, info.normalize_group(name))


def _parse_property(source, info, positive, in_set):
    here = source.pos
    if source.match("{"):
        negate = source.match("^")
        prop_name, name = _parse_property_name(source)
        if source.match("}"):
            if name in PROPERTIES:
                return Property(PROPERTIES[name], positive != negate)
    source.pos = here
    return make_character(info, ord("p" if positive else "P"), in_set)


def _parse_property_name(source):
    b = StringBuilder(5)
    while True:
        here = source.pos
        ch = source.get()
        if ch.isalnum():
            b.append(ch)
        else:
            source.pos = here
            break
    name = b.build()
    return name, name


def _parse_octal_escape(source, info, digits, in_set):
    # Up to three octal digits, counting the ones already read.
    while len(digits) < 3:
        here = source.pos
        ch = source.get()
        if ch and "0" <= ch <= "7":
            digits += ch
        else:
            source.pos = here
            break
    value = 0
    for digit in digits:
        value = value * 8 + (ord(digit) - ord("0"))
    return make_character(info, value & 0xff, in_set)


def _parse_hex_digits(source, max_digits):
    value = 0
    count = 0
    while count < max_digits:
        here = source.pos
        c = source.get()
        if c and c in "0123456789abcdefABCDEF":
            value = value * 16 + int(c, 16)
            count += 1
        else:
            source.pos = here
            break
    if count == 0:
        raise RegexpError("invalid hex escape")
    return value


def _make_code_point(info, value, in_set):
    """A character given by code point, matched as its UTF-8 bytes. In a set
    only single-byte characters can be expressed."""
    if value < 0x80:
        return make_character(info, value, in_set)
    if value < 0x800:
        units = [0xc0 | (value >> 6), 0x80 | (value & 0x3f)]
    elif value < 0x10000:
        units = [0xe0 | (value >> 12), 0x80 | ((value >> 6) & 0x3f),
                 0x80 | (value & 0x3f)]
    else:
        units = [0xf0 | (value >> 18), 0x80 | ((value >> 12) & 0x3f),
                 0x80 | ((value >> 6) & 0x3f), 0x80 | (value & 0x3f)]
    if in_set:
        return CodePoint(value)
    items = []
    for unit in units:
        items.append(Character(unit))
    return Sequence(items)


def _parse_numeric_escape(source, info, ch, in_set):
    if ch in "89":
        if in_set:
            return make_character(info, ord(ch[0]), in_set)
    elif in_set or ch == "0":
        # \0, \0nn, and any digit escape in a set, are octal.
        return _parse_octal_escape(source, info, ch, in_set)
    # \1 to \9 are backreferences. A longer number is a backreference if
    # there are that many groups, and an octal escape otherwise.
    start = source.pos
    digits = ch
    while True:
        here = source.pos
        c = source.get()
        if c and c.isdigit():
            digits += c
        else:
            source.pos = here
            break
    if len(digits) > 1 and int(digits) > info.group_count:
        source.pos = start
        if ch in "89":
            return make_character(info, ord(ch[0]), in_set)
        return _parse_octal_escape(source, info, ch, in_set)
    return make_ref_group(info, int(digits))


def _parse_posix_class(source, info):
    negate = source.match("^")
    prop_name, name = _parse_property_name(source)
    if not source.match(":]"):
        raise ParseError
    try:
        return Property(PROPERTIES[name], positive=not negate)
    except KeyError:
        try:
            return _posix_class_as_set(name, negate, info)
        except KeyError:
            raise ParseError


def _posix_class_as_set(name, negate, info):
    item = SetUnion(info, EXTRA_POSIX_PROPERTIES[name])
    if negate:
        item = item.with_flags(positive=not item.positive)
    return item


def _compile_no_cache(pattern, flags):
    source = Source(pattern)
    if flags & EXTENDED:
        source.ignore_space = True
    info = Info(flags)
    parsed = _parse_pattern(source, info)

    if not source.at_end():
        raise RegexpError("trailing characters in pattern")

    parsed.fix_groups()
    parsed = parsed.optimize(info)

    ctx = CompilerContext()
    parsed.compile(ctx)
    ctx.emit(OPCODE_SUCCESS)
    code = ctx.build()

    # Ruby numbers the groups it can see: not the hidden ones, and, when
    # there are named groups, only those (plain groups do not capture).
    # group_offsets maps a visible group's number to the actual one.
    has_names = len(info.group_index) > 0
    group_offsets = []
    to_visible = {}
    for group in range(1, info.group_count + 1):
        if group in info.hidden_groups:
            continue
        if has_names and group not in info.group_name:
            continue
        to_visible[group] = len(group_offsets) + 1
        group_offsets.append(group - (len(group_offsets) + 1))
    group_index = {}
    index_group = {}
    for n, v in info.group_index.iteritems():
        visible = to_visible.get(v, -1)
        if visible != -1:
            group_index[n] = visible
            index_group[visible] = n
    pattern = CompiledPattern(code, info.flags)
    return pattern, info.flags, info.group_count, group_index, index_group, group_offsets


def compile(cache, pattern, flags=0):
    if not cache.contains(pattern, flags):
        cache.set(pattern, flags, _compile_no_cache(pattern, flags))
    return cache.get(pattern, flags)
