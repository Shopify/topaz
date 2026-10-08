import copy

from topaz.astcompiler import SymbolTable
from topaz.closure import ClosureCell
from topaz.module import ClassDef
from topaz.objects.objectobject import W_Object


class W_BindingObject(W_Object):
    classdef = ClassDef("Binding", W_Object.classdef)
    # names and cells grow when local_variable_set defines a variable.
    _immutable_fields_ = ["w_self", "lexical_scope"]

    def __init__(self, space, names, cells, w_self, lexical_scope):
        W_Object.__init__(self, space)
        self.names = names[:]
        self.cells = cells[:]
        self.w_self = w_self
        self.lexical_scope = lexical_scope

    def __deepcopy__(self, memo):
        obj = super(W_BindingObject, self).__deepcopy__(memo)
        obj.names = self.names[:]
        obj.cells = copy.deepcopy(self.cells, memo)
        obj.w_self = copy.deepcopy(self.w_self, memo)
        obj.lexical_scope = copy.deepcopy(self.lexical_scope, memo)
        return obj

    classdef.undefine_allocator()

    @classdef.method("dup")
    @classdef.method("clone")
    def method_dup(self, space, args_w):
        # A copy sharing the same variables (ERB evaluates templates in
        # TOPLEVEL_BINDING.dup).
        return W_BindingObject(space, self.names, self.cells, self.w_self, self.lexical_scope)

    @classdef.method("eval", source="str", filepath="str", lineno="int")
    def method_eval(self, space, source, filepath="(eval)", lineno=1):
        symtable = SymbolTable()
        for name in self.names:
            symtable.cells[name] = symtable.FREEVAR
        bc = space.compile(source, filepath, initial_lineno=lineno, symtable=symtable)
        frame = space.create_frame(bc, w_self=self.w_self, lexical_scope=self.lexical_scope)
        # The compiled code orders its free variables its own way; match
        # them to the binding's cells by name.
        for idx in range(len(bc.freevars)):
            name = bc.freevars[idx]
            for j in range(len(self.names)):
                if self.names[j] == name:
                    frame.set_cell(idx + len(bc.cellvars), self.cells[j])
                    break
        with space.getexecutioncontext().visit_frame(frame):
            return space.execute_frame(frame, bc)

    def find_local(self, name):
        for j in range(len(self.names)):
            if self.names[j] == name:
                return j
        return -1

    @classdef.method("local_variable_get", name="symbol")
    def method_local_variable_get(self, space, name):
        j = self.find_local(name)
        if j < 0:
            raise space.error(space.w_NameError,
                "local variable '%s' is not defined for %s" % (
                    name, space.any_to_s(self)))
        w_value = self.cells[j].get(space, None, 0)
        return w_value if w_value is not None else space.w_nil

    @classdef.method("local_variable_set", name="symbol")
    def method_local_variable_set(self, space, name, w_value):
        j = self.find_local(name)
        if j < 0:
            # A new variable, visible to code evaluated in this binding.
            self.names.append(name)
            self.cells.append(ClosureCell(w_value))
            return w_value
        self.cells[j].set(space, None, 0, w_value)
        return w_value

    @classdef.method("local_variable_defined?", name="symbol")
    def method_local_variable_definedp(self, space, name):
        return space.newbool(self.find_local(name) >= 0)

    @classdef.method("local_variables")
    def method_local_variables(self, space):
        return space.newarray([
            space.newsymbol(name) for name in self.names
            # Hidden temporaries (%tmp1 and the like) are not variables.
            if name and name[0] != "%"
        ])

    @classdef.method("receiver")
    def method_receiver(self, space):
        return self.w_self
