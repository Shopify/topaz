from rpython.rlib import jit

from topaz.closure import BaseCell, ClosureCell, LOCAL_CELL
from topaz.objects.hashobject import W_HashObject
from topaz.objects.moduleobject import W_ModuleObject


# The remaining bits hold the entry PC. These flags are not virtualizable.
VISIBILITY_MASK = 3
ESCAPED_FLAG = 4
ENTRY_PC_SHIFT = 3
FRAME_FLAGS_MASK = (1 << ENTRY_PC_SHIFT) - 1


class BaseFrame(object):
    _attrs_ = ["backref", "flags", "back_last_instr"]

    def __init__(self):
        self.backref = jit.vref_None
        # Public visibility, not escaped, entry PC zero.
        self.flags = 0

    def is_escaped(self):
        return bool(self.flags & ESCAPED_FLAG)

    def set_escaped(self, escaped):
        if escaped:
            self.flags |= ESCAPED_FLAG
        else:
            self.flags &= ~ESCAPED_FLAG


class Frame(BaseFrame):
    _virtualizable_ = [
        "bytecode", "localsstack_w[*]", "stackpos", "w_self", "block",
        "lastblock", "lexical_scope", "last_instr",
        "parent_interp", "top_parent_interp", "kwargs_given",
    ]

    @jit.unroll_safe
    def __init__(self, bytecode, w_self, lexical_scope, block, parent_interp,
                 top_parent_interp, regexp_match_cell):
        self = jit.hint(self, fresh_virtualizable=True, access_directly=True)
        BaseFrame.__init__(self)
        self.bytecode = bytecode
        # Local values, operand stack, then local/free-variable cells.
        # Keep the value and cell slots separate so local access still
        # dispatches on the cell type, not the Ruby value's type.
        num_locals = len(bytecode.cellvars)
        cells_start = num_locals + bytecode.max_stackdepth
        self.localsstack_w = [None] * (
            cells_start + num_locals + len(bytecode.freevars))
        for i in xrange(num_locals):
            self.localsstack_w[cells_start + i] = LOCAL_CELL
        self.stackpos = len(bytecode.cellvars)
        self.last_instr = 0
        # One bit per keyword argument with a default that was passed:
        # the code's prologue computes the others' defaults.
        self.kwargs_given = 0
        self.regexp_match_cell = regexp_match_cell
        self.w_self = w_self
        self.lexical_scope = lexical_scope
        self.block = block
        self.parent_interp = parent_interp
        self.top_parent_interp = top_parent_interp
        self.lastblock = None
        # The module that owns the running method, for `super`; None when
        # not known (then the lexical scope is used).
        self.w_owner = None
        # The name `super` calls: set in define_method bodies, whose code
        # was compiled inside some other method.
        self.super_name = None

    def get_regexp_match_cell(self):
        # Blocks must capture the shared cell even if no match has happened
        # yet, so later updates remain visible in the enclosing scope.
        cell = self.regexp_match_cell
        if cell is None:
            cell = self.regexp_match_cell = ClosureCell(None)
        return cell

    def get_entry_pc(self):
        return self.flags >> ENTRY_PC_SHIFT

    def set_entry_pc(self, pc):
        assert pc >= 0
        self.flags = (self.flags & FRAME_FLAGS_MASK) | (pc << ENTRY_PC_SHIFT)

    def get_visibility(self):
        return self.flags & VISIBILITY_MASK

    def set_visibility(self, visibility):
        assert 0 <= visibility <= VISIBILITY_MASK
        self.flags = (self.flags & ~VISIBILITY_MASK) | visibility

    def get_cell(self, pos):
        assert pos >= 0
        offset = len(self.bytecode.cellvars) + self.bytecode.max_stackdepth
        cell = self.localsstack_w[offset + pos]
        assert isinstance(cell, BaseCell)
        return cell

    def set_cell(self, pos, cell):
        assert pos >= 0
        offset = len(self.bytecode.cellvars) + self.bytecode.max_stackdepth
        self.localsstack_w[offset + pos] = cell

    def _set_arg(self, space, pos, w_value):
        assert pos >= 0
        self.get_cell(pos).set(space, self, pos, w_value)

    def handle_block_args(self, space, bytecode, args_w, block):
        # Keep keyword arguments out of the auto-splatting and trimming of
        # the positional ones below.
        w_keywords = None
        if args_w and (len(bytecode.kwarg_names) > 0 or
                       bytecode.kwrest_pos != -1):
            w_last = args_w[-1]
            if isinstance(w_last, W_HashObject) and w_last.is_keywords:
                w_keywords = w_last
                end = len(args_w) - 1
                assert end >= 0
                args_w = args_w[:end]
        if (len(args_w) == 1 and (
                len(bytecode.arg_pos) >= 2 or (
                    len(bytecode.arg_pos) > 0 and
                    bytecode.splat_arg_pos != -1))):
            w_arg = args_w[0]
            if (not space.is_kind_of(w_arg, space.w_array) and
                    space.respond_to(w_arg, "to_ary")):
                w_arg = space.convert_type(w_arg, space.w_array, "to_ary",
                                           raise_error=True,
                                           reraise_error=True)
            if space.is_kind_of(w_arg, space.w_array):
                # A copy: the padding and trimming below must not change
                # the array.
                args_w = space.listview(w_arg)[:]
        minargc = len(bytecode.arg_pos) - bytecode.num_defaults
        if len(args_w) < minargc:
            args_w.extend([space.w_nil] * (minargc - len(args_w)))
        if bytecode.splat_arg_pos == -1:
            if len(args_w) > len(bytecode.arg_pos):
                del args_w[len(bytecode.arg_pos):]
        if w_keywords is not None:
            args_w.append(w_keywords)
        return self.handle_args(space, bytecode, args_w, block)

    @jit.unroll_safe
    def handle_args(self, space, bytecode, args_w, block):

        keywords_hash = None
        if args_w:
            w_last = args_w[-1]
            if isinstance(w_last, W_HashObject) and w_last.is_keywords:
                # Keyword arguments (Ruby 3.0 semantics: an ordinary hash
                # argument never binds to keyword parameters).
                end = len(args_w) - 1
                assert end >= 0
                if len(bytecode.kwarg_names) > 0 or bytecode.kwrest_pos != -1:
                    keywords_hash = w_last.copy_keywords(space)
                    args_w = args_w[:end]
                elif w_last.size() == 0:
                    # `f(**{})` passes nothing.
                    args_w = args_w[:end]
                elif not bytecode.ruby2_keywords:
                    # A method without keyword parameters gets them as a
                    # positional hash.
                    w_last.is_keywords = False

        if (bytecode.num_kw_defaults < len(bytecode.kwarg_names) and
                not keywords_hash):
            # The keywords without defaults come last.
            missing = []
            for j in range(bytecode.num_kw_defaults, len(bytecode.kwarg_names)):
                missing.append(":" + bytecode.kwarg_names[j])
            raise space.error(
                space.w_ArgumentError,
                "%s: %s" % ("missing keyword" if len(missing) == 1 else "missing keywords",
                            ", ".join(missing)))

        pre = 0
        post = len(args_w)

        if (post < (len(bytecode.arg_pos) - bytecode.num_defaults) or
                (bytecode.splat_arg_pos == -1 and
                    post > len(bytecode.arg_pos))):
            required = len(bytecode.arg_pos) - bytecode.num_defaults
            if bytecode.splat_arg_pos != -1:
                expected = "%d+" % required
            elif bytecode.num_defaults > 0:
                expected = "%d..%d" % (required, len(bytecode.arg_pos))
            else:
                expected = "%d" % required
            raise space.error(
                space.w_ArgumentError,
                "wrong number of arguments (given %d, expected %s)" % (
                    len(args_w), expected))

        if bytecode.default_arg_begin != -1:
            len_pre_args = bytecode.default_arg_begin
        elif bytecode.splat_arg_pos != -1:
            len_pre_args = bytecode.splat_arg_pos
        else:
            len_pre_args = len(bytecode.arg_pos)
        len_post_arg = (len(bytecode.arg_pos) - bytecode.num_defaults -
                        len_pre_args)

        # [required args, optional args, splat arg, required args, keywords args, keyword rest, block]
        #  ^                                                      ^
        # pre                                                   post

        # fill post-arguments from back.
        actual_args_len = post
        offset = len(bytecode.arg_pos) - post
        for i in xrange(actual_args_len - 1, actual_args_len - len_post_arg - 1, -1):
            self._set_arg(space, bytecode.arg_pos[i + offset], args_w[i])
            post -= 1
        # [required args, optional args, splat arg, required args, keywords args, keyword rest, block]
        #  ^                                       ^-------------
        # pre                                    post

        # fill arguments from start as far as we can (until we hit post or the
        # end of the default arguments + normal arguments
        for i in xrange(min(post, len_pre_args + bytecode.num_defaults)):
            self._set_arg(space, bytecode.arg_pos[i], args_w[i])
            pre += 1
        # [required args, optional args, splat arg, required args, keywords args, keyword rest, block]
        #  ------------------------^               ^
        #                         pre            post

        given_defaults = pre - len_pre_args
        # The code's prologue computes the rest.
        if bytecode.num_defaults > 0:
            if given_defaults < 0:
                given_defaults = 0
            self.set_entry_pc(bytecode.default_entry_pcs[given_defaults])

        if bytecode.splat_arg_pos != -1:
            if pre >= post:
                splat_args_w = []
            else:
                splat_args_w = args_w[pre:post]
            w_splat_args = space.newarray(splat_args_w)
            self._set_arg(space, bytecode.splat_arg_pos, w_splat_args)

        for i, name in enumerate(bytecode.kwarg_names):
            w_key = space.newsymbol(name)
            w_value = None
            if keywords_hash is not None:
                try:
                    w_value = keywords_hash.getitem(w_key)
                    keywords_hash.delete(w_key)
                except KeyError:
                    pass
            # kword arguments with defaults come first, so if we get an
            # index error here, we're missing a required keyword argument
            if w_value is not None:
                if i < bytecode.num_kw_defaults:
                    self.kwargs_given |= 1 << i
            elif i < bytecode.num_kw_defaults:
                # The code's prologue computes the default.
                continue
            else:
                missing = []
                for j in range(i, len(bytecode.kwarg_names)):
                    present = False
                    if keywords_hash is not None:
                        try:
                            keywords_hash.getitem(space.newsymbol(bytecode.kwarg_names[j]))
                            present = True
                        except KeyError:
                            pass
                    if not present:
                        missing.append(":" + bytecode.kwarg_names[j])
                raise space.error(
                    space.w_ArgumentError,
                    "%s: %s" % ("missing keyword" if len(missing) == 1 else "missing keywords",
                                ", ".join(missing)))
            self._set_arg(space, bytecode.cellvars.index(name), w_value)

        self.bytecode = bytecode

        if bytecode.kwrest_pos != -1:
            if keywords_hash is not None:
                self._set_arg(space, bytecode.kwrest_pos, keywords_hash)
            else:
                self._set_arg(space, bytecode.kwrest_pos, space.newhash())
        elif keywords_hash is not None:
            if keywords_hash.size() > 0:
                raise space.error(
                    space.w_ArgumentError,
                    "unknown keywords: %s" % space.str_w(
                        space.send(space.send(keywords_hash, "keys"), "to_s")
                    ))

        if bytecode.block_arg_pos != -1:
            if block is None:
                w_block = space.w_nil
            else:
                w_block = block.copy(space)
            self._set_arg(space, bytecode.block_arg_pos, w_block)

    def push(self, w_obj):
        stackpos = jit.promote(self.stackpos)
        self.localsstack_w[stackpos] = w_obj
        self.stackpos = stackpos + 1

    def pop(self):
        stackpos = jit.promote(self.stackpos) - 1
        assert stackpos >= 0
        w_res = self.localsstack_w[stackpos]
        self.localsstack_w[stackpos] = None
        self.stackpos = stackpos
        return w_res

    @jit.unroll_safe
    def popitemsreverse(self, n):
        items_w = [None] * n
        for i in xrange(n - 1, -1, -1):
            items_w[i] = self.pop()
        return items_w

    def peek(self):
        stackpos = jit.promote(self.stackpos) - 1
        assert stackpos >= 0
        return self.localsstack_w[stackpos]

    def popblock(self):
        lastblock = self.lastblock
        if lastblock is not None:
            self.lastblock = lastblock.lastblock
        return lastblock

    @jit.unroll_safe
    def unrollstack(self, kind):
        while self.lastblock is not None:
            block = self.popblock()
            if block.handling_mask & kind:
                return block
            block.cleanupstack(self)

    def unrollstack_and_jump(self, space, unroller):
        block = self.unrollstack(unroller.kind)
        return block.handle(space, self, unroller)

    def has_contents(self):
        return True

    def get_filename(self):
        return self.bytecode.filepath

    def get_lineno(self, prev_frame):
        if prev_frame is None:
            instr = self.last_instr
        else:
            instr = prev_frame.back_last_instr - 1
        try:
            return self.bytecode.lineno_table[instr]
        except IndexError:
            return self.last_instr

    def get_code_name(self):
        return self.bytecode.name

    def get_backtrace_label(self):
        """The label for this frame in a backtrace, as Ruby 3.4 writes
        them: 'Foo#bar', 'Foo.baz', 'block (2 levels) in Foo#bar',
        '<main>'."""
        name = self.bytecode.name
        levels = 0
        while name.startswith("block in "):
            levels += 1
            name = name[len("block in "):]
        if not name.startswith("<"):
            name = self._qualify_method_name(name)
        if levels == 0:
            return name
        elif levels == 1:
            return "block in %s" % name
        return "block (%d levels) in %s" % (levels, name)

    def _qualify_method_name(self, name):
        scope = self.lexical_scope
        if scope is None:
            # Methods defined at the top level are methods of Object.
            return "Object#%s" % name
        w_mod = scope.w_mod
        if not isinstance(w_mod, W_ModuleObject) or w_mod.name is None:
            return name
        if self.w_self is w_mod:
            return "%s.%s" % (w_mod.name, name)
        return "%s#%s" % (w_mod.name, name)


class BuiltinFrame(BaseFrame):
    def __init__(self, name, w_owner=None, w_receiver=None):
        BaseFrame.__init__(self)
        self.name = name
        self.w_owner = w_owner
        self.w_receiver = w_receiver

    def has_contents(self):
        return self.backref() is not None

    def get_filename(self):
        return self.backref().get_filename()

    def get_lineno(self, prev_frame):
        return self.backref().get_lineno(self)

    def get_code_name(self):
        return self.name

    def get_backtrace_label(self):
        w_owner = self.w_owner
        if w_owner is None or w_owner.name is None:
            return self.name
        if self.w_receiver is w_owner:
            return "%s.%s" % (w_owner.name, self.name)
        return "%s#%s" % (w_owner.name, self.name)
