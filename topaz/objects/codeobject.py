import copy

from rpython.rlib import rvmprof

from topaz.module import ClassDef
from topaz.objects.objectobject import W_BaseObject


def _vmprof_safe(s):
    # vmprof names must not contain extra ':' and must stay short.
    if len(s) > 200:
        s = s[:197] + "..."
    return s.replace(":", ";")


def get_vmprof_name(code):
    return "rb:%s:%d:%s" % (
        _vmprof_safe(code.name), code.lineno, _vmprof_safe(code.filepath)
    )


class W_CodeObject(W_BaseObject):
    _immutable_fields_ = [
        "code", "consts_w[*]", "max_stackdepth", "cellvars[*]", "freevars[*]",
        "arg_pos[*]", "defaults[*]", "block_arg_pos", "splat_arg_pos",
        "kwarg_names[*]", "kwrest_pos", "num_kw_defaults", "default_arg_begin", "num_defaults",
        "filepath", "lineno", "default_entry_pcs[*]",
    ]

    classdef = ClassDef("Code", W_BaseObject.classdef)

    def __init__(self, name, filepath, line, code, max_stackdepth, consts, args,
                 splat_arg, kwargs, kwrest_arg, block_arg,
                 defaults, first_default_arg, kw_defaults,
                 cellvars, freevars, lineno_table, default_entry_pcs=None):

        self.name = name
        self.filepath = filepath
        self.lineno = line
        self.code = code
        self.max_stackdepth = max_stackdepth
        self.consts_w = consts
        # How many optional positional and keyword arguments have defaults
        # (computed in the code's prologue).
        self.num_defaults = len(defaults)
        # A fixed-size copy: the field is immutable, the list given grew.
        kwarg_names = [""] * len(kwargs)
        for i in range(len(kwargs)):
            kwarg_names[i] = kwargs[i]
        self.kwarg_names = kwarg_names
        self.num_kw_defaults = len(kw_defaults)
        self.cellvars = cellvars
        self.freevars = freevars
        self.lineno_table = lineno_table
        # A fixed-size copy (the field is immutable).
        if default_entry_pcs is None:
            default_entry_pcs = []
        entry_pcs = [0] * len(default_entry_pcs)
        for i in range(len(default_entry_pcs)):
            entry_pcs[i] = default_entry_pcs[i]
        self.default_entry_pcs = entry_pcs

        n_args = len(args)
        arg_pos = [-1] * n_args
        for idx, arg in enumerate(args):
            arg_pos[idx] = cellvars.index(arg)
        self.arg_pos = arg_pos

        default_arg_begin = -1
        if first_default_arg:
            default_arg_begin = cellvars.index(first_default_arg)
        self.default_arg_begin = default_arg_begin

        splat_arg_pos = -1
        if splat_arg is not None:
            splat_arg_pos = cellvars.index(splat_arg)
        self.splat_arg_pos = splat_arg_pos

        kwrest_pos = -1
        if kwrest_arg is not None:
            kwrest_pos = cellvars.index(kwrest_arg)
        self.kwrest_pos = kwrest_pos

        block_arg_pos = -1
        if block_arg is not None:
            block_arg_pos = cellvars.index(block_arg)
        self.block_arg_pos = block_arg_pos

        # Set by Module#ruby2_keywords: keyword arguments collected by the
        # rest parameter stay keywords when splatted into another call.
        self.ruby2_keywords = False
        # Instructions and entries run outside compiled code (see
        # Topaz.interp_profile).
        self.interp_instrs = 0
        self.interp_entries = 0

        rvmprof.register_code(self, get_vmprof_name)

    def __deepcopy__(self, memo):
        obj = super(W_CodeObject, self).__deepcopy__(memo)
        obj.name = self.name
        obj.filepath = self.filepath
        obj.lineno = self.lineno
        obj.code = self.code
        obj.max_stackdepth = self.max_stackdepth
        obj.default_entry_pcs = self.default_entry_pcs
        obj.interp_instrs = 0
        obj.interp_entries = 0
        obj.consts_w = copy.deepcopy(self.consts_w, memo)
        obj.num_defaults = self.num_defaults
        obj.cellvars = self.cellvars
        obj.freevars = self.freevars
        obj.lineno_table = self.lineno_table
        obj.arg_pos = self.arg_pos
        obj.block_arg_pos = self.block_arg_pos
        obj.splat_arg_pos = self.splat_arg_pos
        obj.default_arg_begin = self.default_arg_begin
        obj.num_kw_defaults = self.num_kw_defaults
        obj.kwrest_pos = self.kwrest_pos
        obj.kwarg_names = self.kwarg_names
        obj.ruby2_keywords = self.ruby2_keywords
        return obj

    def parameters(self, space, is_lambda):
        """Method#parameters and Proc#parameters: [type, name] pairs. A
        proc's required arguments are optional. Arguments after a rest
        argument are listed before it."""
        params_w = []
        first_default = -1
        if self.default_arg_begin != -1:
            for i in range(len(self.arg_pos)):
                if self.arg_pos[i] == self.default_arg_begin:
                    first_default = i
                    break
        for i in range(len(self.arg_pos)):
            name = self.cellvars[self.arg_pos[i]]
            if first_default != -1 and first_default <= i < first_default + self.num_defaults:
                kind = "opt"
            else:
                kind = "req" if is_lambda else "opt"
            params_w.append(self._parameter(space, kind, name))
        if self.splat_arg_pos != -1:
            params_w.append(self._parameter(space, "rest", self.cellvars[self.splat_arg_pos]))
        for i in range(len(self.kwarg_names)):
            kind = "key" if i < self.num_kw_defaults else "keyreq"
            params_w.append(self._parameter(space, kind, self.kwarg_names[i]))
        if self.kwrest_pos != -1:
            params_w.append(self._parameter(space, "keyrest", self.cellvars[self.kwrest_pos]))
        if self.block_arg_pos != -1:
            params_w.append(self._parameter(space, "block", self.cellvars[self.block_arg_pos]))
        return space.newarray(params_w)

    def _parameter(self, space, kind, name):
        items_w = [space.newsymbol(kind)]
        # Hidden names (an unnamed destructuring argument) are left out.
        if name and (name[0].isalpha() or name[0] == "_" or name in ["*", "**", "&"] or ord(name[0]) >= 0x80):
            items_w.append(space.newsymbol(name))
        return space.newarray(items_w)

    def arity(self, negative_defaults=False):
        args_count = len(self.arg_pos) - self.num_defaults
        if self.splat_arg_pos != -1 or (negative_defaults and self.num_defaults > 0):
            args_count = -(args_count + 1)
        return args_count

    @classdef.method("filepath")
    def method_filepath(self, space):
        return space.newstr_fromstr(self.filepath)


rvmprof.register_code_object_class(W_CodeObject, get_vmprof_name)
