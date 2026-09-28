from topaz.module import ClassDef
from topaz.objects.objectobject import W_Object


class W_ProcObject(W_Object):
    classdef = ClassDef("Proc", W_Object.classdef)
    _immutable_fields_ = [
        "bytecode", "w_self", "lexical_scope", "cells[*]",
        "block", "parent_interp", "top_parent_interp",
        "regexp_match_cell", "is_lambda"]

    def __init__(self, space, bytecode, w_self, lexical_scope, cells, block,
                 parent_interp, top_parent_interp, regexp_match_cell,
                 is_lambda):
        W_Object.__init__(self, space)
        self.bytecode = bytecode
        self.w_self = w_self
        self.lexical_scope = lexical_scope
        self.cells = cells
        self.block = block
        self.parent_interp = parent_interp
        self.top_parent_interp = top_parent_interp
        self.regexp_match_cell = regexp_match_cell
        self.is_lambda = is_lambda
        # Set for procs made by Kernel#proc and Proc.new: the call their
        # block was given to has returned, so `break` in them is an error.
        # A block captured with &blk breaks out of the method it was given
        # to, even when called with Proc#call.
        self.orphan_break = False
        # The owner of the method the block was created in, for `super`,
        # and the method's name when the block is a define_method body.
        self.w_owner = None
        self.super_name = None

    def copy(self, space, w_self=None, lexical_scope=None, is_lambda=False):
        w_proc = W_ProcObject(
            space, self.bytecode,
            w_self or self.w_self,
            lexical_scope or self.lexical_scope,
            self.cells, self.block, self.parent_interp, self.top_parent_interp,
            self.regexp_match_cell,
            is_lambda or self.is_lambda
        )
        w_proc.w_owner = self.w_owner
        w_proc.super_name = self.super_name
        return w_proc

    def orphan_copy(self, space):
        w_proc = self.copy(space)
        w_proc.orphan_break = True
        return w_proc

    @classdef.singleton_method("new")
    def method_new(self, space, block):
        if block is None:
            block = space.getexecutioncontext().gettoprubyframe().block
        if block is None:
            raise space.error(space.w_ArgumentError, "tried to create Proc object without a block")
        return block.orphan_copy(space)

    method_allocate = classdef.undefine_allocator()

    @classdef.method("yield")
    @classdef.method("===")
    @classdef.method("[]")
    @classdef.method("call")
    def method_call(self, space, args_w, block):
        from topaz.interpreter import RaiseReturn, RaiseBreak

        try:
            return space.invoke_block(self, args_w, block_arg=block)
        except RaiseReturn as e:
            if self.is_lambda:
                return e.w_value
            else:
                raise
        except RaiseBreak as e:
            if e.parent_interp is not self.parent_interp:
                # A break from a block nested in this proc, headed for a
                # frame further out.
                raise
            if self.is_lambda:
                return e.w_value
            elif self.orphan_break:
                raise space.error(space.w_LocalJumpError, "break from proc-closure")
            else:
                raise

    @classdef.method("__topaz_set_last_match")
    def method_topaz_set_last_match(self, space, w_match):
        """Sets $~ as the block sees it: for methods written in Ruby that
        match on the block's behalf (Enumerable#grep)."""
        if self.regexp_match_cell is not None:
            self.regexp_match_cell.set(space, None, 0, w_match)
        return w_match

    @classdef.method("ruby2_keywords")
    def method_ruby2_keywords(self, space):
        # Keywords collected by the block's *rest stay marked as keywords
        # (delegate.rb's delegating blocks). The mark is on the code.
        self.bytecode.ruby2_keywords = True
        return self

    @classdef.method("parameters")
    def method_parameters(self, space, w_opts=None):
        is_lambda = self.is_lambda
        if w_opts is not None and w_opts is not space.w_nil:
            # parameters(lambda: true) reports a proc as if it were a lambda.
            w_lambda = space.send(w_opts, "[]", [space.newsymbol("lambda")])
            if w_lambda is not space.w_nil:
                is_lambda = space.is_true(w_lambda)
        return self.bytecode.parameters(space, is_lambda)

    @classdef.method("lambda?")
    def method_lambda(self, space):
        return space.newbool(self.is_lambda)

    @classdef.method("arity")
    def method_arity(self, space):
        return space.newint(self.bytecode.arity(negative_defaults=self.is_lambda))

    @classdef.method("binding")
    def method_binding(self, space):
        return space.newbinding_fromblock(self)

    @classdef.method("source_location")
    def method_source_location(self, space):
        return space.newarray([
            space.newstr_fromstr(self.bytecode.filepath),
            space.newint(self.bytecode.lineno)
        ])
