"""Translate Prism's syntax tree (topaz.prism.nodes) into Topaz's AST.

The translator also builds the symbol tables the compiler needs, the same
way the old parser did while parsing: a SymbolTable per method, class and
module body, a BlockSymbolTable per block, declaring arguments, local
reads and local writes as it goes.
"""

from topaz import ast
from topaz.astcompiler import (
    SymbolTable, BlockSymbolTable, SharedScopeSymbolTable)
from topaz.prism import nodes
from topaz.utils import regexp


class TranslateError(Exception):
    def __init__(self, msg, lineno):
        self.msg = msg
        self.lineno = lineno


def _int_node(value):
    try:
        return ast.ConstantInt(value.toint())
    except OverflowError:
        return ast.ConstantBigInt(value)


def _regexp_flags(node):
    flags = 0
    if node.has_flag(nodes.REGULAR_EXPRESSION_FLAGS_IGNORE_CASE):
        flags |= regexp.IGNORE_CASE
    if node.has_flag(nodes.REGULAR_EXPRESSION_FLAGS_EXTENDED):
        flags |= regexp.EXTENDED
    if node.has_flag(nodes.REGULAR_EXPRESSION_FLAGS_MULTI_LINE):
        flags |= regexp.DOT_ALL
    if node.has_flag(nodes.REGULAR_EXPRESSION_FLAGS_ONCE):
        flags |= regexp.ONCE
    if (node.has_flag(nodes.REGULAR_EXPRESSION_FLAGS_UTF_8) or
            node.has_flag(nodes.REGULAR_EXPRESSION_FLAGS_EUC_JP) or
            node.has_flag(nodes.REGULAR_EXPRESSION_FLAGS_WINDOWS_31J)):
        flags |= regexp.FIXED_ENCODING
    if node.has_flag(nodes.REGULAR_EXPRESSION_FLAGS_ASCII_8BIT):
        flags |= regexp.NO_ENCODING
    return flags


class Params(object):
    """The parameters of a method or block, in the shape ast.Function and
    ast.SendBlock take them."""

    def __init__(self):
        self.args = []
        self.splat_arg = None
        self.post_args = []
        self.kwargs = []
        self.kwrest_arg = None
        self.block_arg = None


class Translator(nodes.Visitor):
    def __init__(self, loader, symtable):
        self.loader = loader
        self.symtable = symtable
        self.temp_count = 0

    def new_temp(self, lineno):
        """A hidden local variable. Its name is not a valid identifier, so
        it cannot clash with the program's own variables."""
        self.temp_count += 1
        name = "%%tmp%d" % self.temp_count
        self.symtable.declare_write(name)
        return name

    # Helpers

    def error(self, msg, node):
        return TranslateError(msg, self.line(node))

    def unsupported(self, node, what):
        return self.error("%s is not supported" % what, node)

    def line(self, node):
        return self.loader.line_of(node.location.start)

    def line_at(self, location):
        return self.loader.line_of(location.start)

    def push_local_scope(self):
        self.symtable = SymbolTable(self.symtable)

    def push_block_scope(self):
        self.symtable = BlockSymbolTable(self.symtable)

    def push_shared_scope(self):
        self.symtable = SharedScopeSymbolTable(self.symtable)

    def save_and_pop_scope(self, node):
        child_symtable = self.symtable
        child_symtable.parent_symtable.add_subscope(node, child_symtable)
        self.symtable = child_symtable.parent_symtable

    def expr(self, node):
        return node.accept(self)

    def optional(self, node):
        if node is None:
            return ast.Nil()
        return self.expr(node)

    def as_statement(self, node):
        if not isinstance(node, ast.BaseStatement):
            node = ast.Statement(node)
        return node

    def statement_list(self, node):
        """The statements of a StatementsNode (or of any other node standing
        in for a body), each wrapped in a BaseStatement."""
        if node is None:
            return []
        if isinstance(node, nodes.StatementsNode):
            result = []
            for child in node.body:
                result.append(self.statement(child))
            return result
        return [self.statement(node)]

    def statement(self, node):
        if isinstance(node, nodes.RescueModifierNode):
            # `stmt rescue stmt`, as opposed to `x = expr rescue expr`.
            lineno = self.line_at(node.keyword_loc)
            return ast.Statement(ast.TryExcept(
                ast.Block([self.statement(node.expression)]),
                [ast.ExceptHandler(
                    [self.standard_error(lineno)], None,
                    ast.Block([self.statement(node.rescue_expression)])
                )],
                ast.Nil(),
                self.new_temp(lineno)
            ))
        return self.as_statement(self.expr(node))

    def block(self, node):
        """A body: an ast.Block of its statements, or ast.Nil when empty."""
        stmts = self.statement_list(node)
        if not stmts:
            return ast.Nil()
        return ast.Block(stmts)

    def body(self, node):
        """A method, class or block body, which may have rescue, else and
        ensure clauses."""
        if isinstance(node, nodes.BeginNode):
            return self.begin_body(node)
        return self.block(node)

    def begin_body(self, node):
        assert isinstance(node, nodes.BeginNode)
        body = self.block(node.statements)
        else_clause = node.else_clause
        if node.rescue_clause is not None:
            handlers = self.rescue_handlers(node.rescue_clause)
            else_body = ast.Nil()
            if else_clause is not None:
                assert isinstance(else_clause, nodes.ElseNode)
                else_body = self.block(else_clause.statements)
            body = ast.TryExcept(body, handlers, else_body,
                                 self.new_temp(self.line(node)))
        elif else_clause is not None:
            assert isinstance(else_clause, nodes.ElseNode)
            body = ast.TryExcept(
                body, [], self.block(else_clause.statements))
        ensure_clause = node.ensure_clause
        if ensure_clause is not None:
            assert isinstance(ensure_clause, nodes.EnsureNode)
            ensure_body = self.statement_list(ensure_clause.statements)
            if not ensure_body:
                ensure_body = [ast.Statement(ast.Nil())]
            body = ast.TryFinally(body, ast.Block(ensure_body))
        return body

    def rescue_handlers(self, node):
        handlers = []
        while node is not None:
            assert isinstance(node, nodes.RescueNode)
            exceptions = []
            for exc in node.exceptions:
                exceptions.append(self.expr(exc))
            target = None
            if node.reference is not None:
                target = self.target(node.reference)
            handlers.append(ast.ExceptHandler(
                exceptions, target, self.block(node.statements)))
            node = node.subsequent
        return handlers

    def standard_error(self, lineno):
        return ast.LookupConstant(ast.Scope(lineno), "StandardError", lineno)

    def array_or_node(self, arguments):
        """The value of `return`, `break` and `next`."""
        if arguments is None:
            return ast.Nil()
        args = self.call_args(arguments, keywords=False)
        if len(args) == 1:
            return args[0]
        return ast.Array(args)

    # Program structure

    def translate(self, program):
        assert isinstance(program, nodes.ProgramNode)
        return ast.Main(self.block(program.statements))

    def visit_default(self, node):
        raise self.unsupported(node, node.NAME)

    def visit_statements_node(self, node):
        return self.block(node)

    def visit_parentheses_node(self, node):
        if node.body is None:
            return ast.Nil()
        return self.block(node.body)

    def visit_begin_node(self, node):
        return self.begin_body(node)

    # Literals

    def visit_nil_node(self, node):
        return ast.Nil()

    def visit_true_node(self, node):
        return ast.ConstantBool(True)

    def visit_false_node(self, node):
        return ast.ConstantBool(False)

    def visit_self_node(self, node):
        return ast.Self(self.line(node))

    def visit_source_file_node(self, node):
        return ast.File()

    def visit_source_line_node(self, node):
        return ast.Line(self.line(node))

    def visit_integer_node(self, node):
        return _int_node(node.value)

    def visit_float_node(self, node):
        return ast.ConstantFloat(node.value)

    def visit_rational_node(self, node):
        lineno = self.line(node)
        return ast.Send(
            ast.LookupConstant(None, "Kernel", lineno),
            "Rational",
            [_int_node(node.numerator), _int_node(node.denominator)],
            None,
            lineno
        )

    def visit_imaginary_node(self, node):
        lineno = self.line(node)
        return ast.Send(
            ast.LookupConstant(None, "Kernel", lineno),
            "Complex",
            [ast.ConstantInt(0), self.expr(node.numeric)],
            None,
            lineno
        )

    def visit_string_node(self, node):
        return ast.ConstantString(node.unescaped)

    def visit_x_string_node(self, node):
        lineno = self.line(node)
        return ast.Send(
            ast.Self(lineno), "`", [ast.ConstantString(node.unescaped)],
            None, lineno
        )

    def visit_interpolated_x_string_node(self, node):
        lineno = self.line(node)
        return ast.Send(
            ast.Self(lineno), "`", [self.string_parts(node.parts)],
            None, lineno
        )

    def string_parts(self, parts):
        """The parts of an interpolated string, symbol or regexp: an
        ast.ConstantString if none of them are dynamic, else an
        ast.DynamicString."""
        const_str = ""
        components = []
        dynamic = False
        for part in parts:
            if isinstance(part, nodes.StringNode):
                if dynamic:
                    components.append(ast.ConstantString(part.unescaped))
                else:
                    const_str += part.unescaped
            elif isinstance(part, nodes.InterpolatedStringNode):
                inner = self.string_parts(part.parts)
                if isinstance(inner, ast.ConstantString):
                    if dynamic:
                        components.append(inner)
                    else:
                        const_str += inner.strvalue
                else:
                    assert isinstance(inner, ast.DynamicString)
                    if not dynamic:
                        dynamic = True
                        if const_str:
                            components.append(ast.ConstantString(const_str))
                    components.extend(inner.strvalues)
            else:
                if isinstance(part, nodes.EmbeddedStatementsNode):
                    if part.statements is None:
                        continue
                    component = self.block(part.statements)
                elif isinstance(part, nodes.EmbeddedVariableNode):
                    component = self.expr(part.variable)
                else:
                    component = self.expr(part)
                if not dynamic:
                    dynamic = True
                    if const_str:
                        components.append(ast.ConstantString(const_str))
                components.append(component)
        if dynamic:
            return ast.DynamicString(components)
        return ast.ConstantString(const_str)

    def visit_interpolated_string_node(self, node):
        return self.string_parts(node.parts)

    def visit_symbol_node(self, node):
        return ast.ConstantSymbol(node.unescaped)

    def visit_interpolated_symbol_node(self, node):
        value = self.string_parts(node.parts)
        if isinstance(value, ast.ConstantString):
            return ast.ConstantSymbol(value.strvalue)
        return ast.Symbol(value, self.line(node))

    def visit_regular_expression_node(self, node):
        return ast.ConstantRegexp(
            node.unescaped, _regexp_flags(node), self.line(node))

    def visit_interpolated_regular_expression_node(self, node):
        value = self.string_parts(node.parts)
        flags = _regexp_flags(node)
        if isinstance(value, ast.ConstantString):
            return ast.ConstantRegexp(value.strvalue, flags, self.line(node))
        return ast.DynamicRegexp(value, flags)

    def visit_array_node(self, node):
        items = []
        for element in node.elements:
            items.append(self.expr(element))
        return ast.Array(items)

    def visit_splat_node(self, node):
        if node.expression is None:
            # `f(*)` passes on the method's anonymous rest parameter (3.2).
            return ast.Splat(self.anonymous_param(node, "*"))
        return ast.Splat(self.expr(node.expression))

    def anonymous_param(self, node, name):
        """The value of an anonymous parameter: `*`, `**` or `&`, or those
        implied by `...`."""
        if not self.symtable.is_defined(name):
            raise self.error("no anonymous %s parameter" % name, node)
        self.symtable.declare_read(name)
        return ast.Variable(name, self.line(node))

    def visit_hash_node(self, node):
        return self.hash(node.elements)

    def visit_keyword_hash_node(self, node):
        # A hash without braces, e.g. in `[k: 1]`; as the last argument of
        # a call it is keyword arguments instead (see call_args).
        return self.hash(node.elements)

    def hash(self, elements):
        items = []
        current_hash = None
        for element in elements:
            if isinstance(element, nodes.AssocSplatNode):
                lineno = self.line(element)
                if current_hash is None:
                    current_hash = ast.Hash(items)
                elif items:
                    current_hash = ast.Send(
                        current_hash, "merge", [ast.Hash(items)], None,
                        lineno)
                if element.value is None:
                    # `f(**)` (Ruby 3.2)
                    value = self.anonymous_param(element, "**")
                else:
                    value = self.expr(element.value)
                current_hash = ast.Send(
                    current_hash, "merge", [ast.HashSplat(value, lineno)],
                    None, lineno)
                items = []
            else:
                assert isinstance(element, nodes.AssocNode)
                items.append((self.expr(element.key), self.expr(element.value)))
        if current_hash is None:
            return ast.Hash(items)
        if items:
            current_hash = ast.Send(
                current_hash, "merge", [ast.Hash(items)], None,
                current_hash.lineno)
        return current_hash

    def visit_implicit_node(self, node):
        # The value of a hash shorthand, like `x` in `{x:}` (Ruby 3.1).
        return self.expr(node.value)

    def visit_range_node(self, node):
        return ast.Range(
            self.optional(node.left), self.optional(node.right),
            node.has_flag(nodes.RANGE_FLAGS_EXCLUDE_END)
        )

    # Variables and constants

    def visit_local_variable_read_node(self, node):
        self.symtable.declare_read(node.name)
        return ast.Variable(node.name, self.line(node))

    def visit_it_local_variable_read_node(self, node):
        self.symtable.declare_read("it")
        return ast.Variable("it", self.line(node))

    def visit_local_variable_write_node(self, node):
        self.symtable.declare_write(node.name)
        target = ast.Variable(node.name, self.line_at(node.name_loc))
        return ast.Assignment(target, self.expr(node.value))

    def visit_instance_variable_read_node(self, node):
        return ast.InstanceVariable(node.name)

    def visit_instance_variable_write_node(self, node):
        return ast.Assignment(
            ast.InstanceVariable(node.name), self.expr(node.value))

    def visit_class_variable_read_node(self, node):
        return ast.ClassVariable(node.name, self.line(node))

    def visit_class_variable_write_node(self, node):
        return ast.Assignment(
            ast.ClassVariable(node.name, self.line(node)),
            self.expr(node.value))

    def visit_global_variable_read_node(self, node):
        return ast.Global(node.name)

    def visit_global_variable_write_node(self, node):
        return ast.Assignment(ast.Global(node.name), self.expr(node.value))

    def visit_back_reference_read_node(self, node):
        return ast.Global(node.name)

    def visit_numbered_reference_read_node(self, node):
        return ast.Global("$%d" % node.number)

    def visit_constant_read_node(self, node):
        return ast.Constant(node.name, self.line(node))

    def constant_name(self, name, node):
        # Prism only leaves out the name of `A::` when there is a syntax
        # error, which parse() has already reported.
        if name is None:
            raise self.error("missing constant name", node)
        return name

    def visit_constant_path_node(self, node):
        scope = None
        if node.parent is not None:
            scope = self.expr(node.parent)
        return ast.LookupConstant(
            scope, self.constant_name(node.name, node),
            self.line_at(node.name_loc))

    def visit_constant_write_node(self, node):
        return ast.Assignment(
            ast.Constant(node.name, self.line(node)), self.expr(node.value))

    def visit_constant_path_write_node(self, node):
        return ast.Assignment(self.expr(node.target), self.expr(node.value))

    def visit_shareable_constant_node(self, node):
        return self.expr(node.write)

    # Operator assignment, `||=` and `&&=`

    def variable_target(self, node, name):
        self.symtable.declare_write(name)
        return ast.Variable(name, self.line(node))

    def op_assign(self, operator, target, value):
        if operator == "||":
            return ast.OrEqual(target, value)
        elif operator == "&&":
            return ast.AndEqual(target, value)
        return ast.AugmentedAssignment(operator, target, value)

    def visit_local_variable_operator_write_node(self, node):
        target = self.variable_target(node, node.name)
        return ast.AugmentedAssignment(
            node.binary_operator, target, self.expr(node.value))

    def visit_local_variable_or_write_node(self, node):
        target = self.variable_target(node, node.name)
        return ast.OrEqual(target, self.expr(node.value))

    def visit_local_variable_and_write_node(self, node):
        target = self.variable_target(node, node.name)
        return ast.AndEqual(target, self.expr(node.value))

    def visit_instance_variable_operator_write_node(self, node):
        return ast.AugmentedAssignment(
            node.binary_operator, ast.InstanceVariable(node.name),
            self.expr(node.value))

    def visit_instance_variable_or_write_node(self, node):
        return ast.OrEqual(
            ast.InstanceVariable(node.name), self.expr(node.value))

    def visit_instance_variable_and_write_node(self, node):
        return ast.AndEqual(
            ast.InstanceVariable(node.name), self.expr(node.value))

    def visit_class_variable_operator_write_node(self, node):
        return ast.AugmentedAssignment(
            node.binary_operator, ast.ClassVariable(node.name, self.line(node)),
            self.expr(node.value))

    def visit_class_variable_or_write_node(self, node):
        return ast.OrEqual(
            ast.ClassVariable(node.name, self.line(node)),
            self.expr(node.value))

    def visit_class_variable_and_write_node(self, node):
        return ast.AndEqual(
            ast.ClassVariable(node.name, self.line(node)),
            self.expr(node.value))

    def visit_global_variable_operator_write_node(self, node):
        return ast.AugmentedAssignment(
            node.binary_operator, ast.Global(node.name), self.expr(node.value))

    def visit_global_variable_or_write_node(self, node):
        return ast.OrEqual(ast.Global(node.name), self.expr(node.value))

    def visit_global_variable_and_write_node(self, node):
        return ast.AndEqual(ast.Global(node.name), self.expr(node.value))

    def visit_constant_operator_write_node(self, node):
        return ast.AugmentedAssignment(
            node.binary_operator, ast.Constant(node.name, self.line(node)),
            self.expr(node.value))

    def visit_constant_or_write_node(self, node):
        return ast.OrEqual(
            ast.Constant(node.name, self.line(node)), self.expr(node.value))

    def visit_constant_and_write_node(self, node):
        return ast.AndEqual(
            ast.Constant(node.name, self.line(node)), self.expr(node.value))

    def visit_constant_path_operator_write_node(self, node):
        return ast.AugmentedAssignment(
            node.binary_operator, self.expr(node.target),
            self.expr(node.value))

    def visit_constant_path_or_write_node(self, node):
        return ast.OrEqual(self.expr(node.target), self.expr(node.value))

    def visit_constant_path_and_write_node(self, node):
        return ast.AndEqual(self.expr(node.target), self.expr(node.value))

    def attribute_target(self, node, receiver, message_loc, name):
        if node.has_flag(nodes.CALL_NODE_FLAGS_SAFE_NAVIGATION):
            raise self.unsupported(node, "&. with an assignment")
        lineno = self.line(node)
        if message_loc is not None:
            lineno = self.line_at(message_loc)
        return ast.Send(self.expr(receiver), name, [], None, lineno)

    def visit_call_operator_write_node(self, node):
        target = self.attribute_target(
            node, node.receiver, node.message_loc, node.read_name)
        return ast.AugmentedAssignment(
            node.binary_operator, target, self.expr(node.value))

    def visit_call_or_write_node(self, node):
        target = self.attribute_target(
            node, node.receiver, node.message_loc, node.read_name)
        return ast.OrEqual(target, self.expr(node.value))

    def visit_call_and_write_node(self, node):
        target = self.attribute_target(
            node, node.receiver, node.message_loc, node.read_name)
        return ast.AndEqual(target, self.expr(node.value))

    def index_target(self, node, receiver, arguments, block, opening_loc):
        if block is not None:
            raise self.unsupported(node, "a block argument in an index")
        args = []
        if arguments is not None:
            args = self.call_args(arguments, keywords=False)
        return ast.Subscript(
            self.expr(receiver), args, self.line_at(opening_loc))

    def visit_index_operator_write_node(self, node):
        target = self.index_target(
            node, node.receiver, node.arguments, node.block,
            node.opening_loc)
        return ast.AugmentedAssignment(
            node.binary_operator, target, self.expr(node.value))

    def visit_index_or_write_node(self, node):
        target = self.index_target(
            node, node.receiver, node.arguments, node.block,
            node.opening_loc)
        return ast.OrEqual(target, self.expr(node.value))

    def visit_index_and_write_node(self, node):
        target = self.index_target(
            node, node.receiver, node.arguments, node.block,
            node.opening_loc)
        return ast.AndEqual(target, self.expr(node.value))

    # Multiple assignment

    def target(self, node):
        """An assignment target: in a multiple assignment, a rescue clause,
        or a for loop."""
        if isinstance(node, nodes.LocalVariableTargetNode):
            self.symtable.declare_write(node.name)
            return ast.Variable(node.name, self.line(node))
        elif isinstance(node, nodes.InstanceVariableTargetNode):
            return ast.InstanceVariable(node.name)
        elif isinstance(node, nodes.ClassVariableTargetNode):
            return ast.ClassVariable(node.name, self.line(node))
        elif isinstance(node, nodes.GlobalVariableTargetNode):
            return ast.Global(node.name)
        elif isinstance(node, nodes.ConstantTargetNode):
            return ast.Constant(node.name, self.line(node))
        elif isinstance(node, nodes.ConstantPathTargetNode):
            scope = None
            if node.parent is not None:
                scope = self.expr(node.parent)
            return ast.LookupConstant(
                scope, self.constant_name(node.name, node),
                self.line_at(node.name_loc))
        elif isinstance(node, nodes.CallTargetNode):
            if node.has_flag(nodes.CALL_NODE_FLAGS_SAFE_NAVIGATION):
                raise self.unsupported(node, "&. with an assignment")
            name = node.name
            assert name.endswith("=")
            end = len(name) - 1
            assert end >= 0
            return ast.Send(
                self.expr(node.receiver), name[:end], [], None,
                self.line_at(node.message_loc))
        elif isinstance(node, nodes.IndexTargetNode):
            return self.index_target(
                node, node.receiver, node.arguments, node.block,
            node.opening_loc)
        elif isinstance(node, nodes.SplatNode):
            if node.expression is None:
                return ast.Splat(None)
            return ast.Splat(self.target(node.expression))
        elif isinstance(node, nodes.ImplicitRestNode):
            return ast.Splat(None)
        elif isinstance(node, nodes.MultiTargetNode):
            return self.multi_target(node.lefts, node.rest, node.rights)
        raise self.unsupported(node, "assigning to %s" % node.NAME)

    def multi_target(self, lefts, rest, rights):
        targets = []
        for node in lefts:
            targets.append(self.target(node))
        if rest is not None and not isinstance(rest, nodes.ImplicitRestNode):
            targets.append(self.target(rest))
        for node in rights:
            targets.append(self.target(node))
        return ast.MultiAssignable(targets)

    def visit_multi_write_node(self, node):
        assignable = self.multi_target(node.lefts, node.rest, node.rights)
        return ast.MultiAssignment(assignable, self.expr(node.value))

    # Calls

    def call_args(self, arguments, keywords=True):
        """The arguments of a call. With `keywords`, a braceless hash in
        them (`f(k: 1)`, `f(**h)`) is keyword arguments (Ruby 3.0), not an
        ordinary hash argument."""
        assert isinstance(arguments, nodes.ArgumentsNode)
        args = []
        for arg in arguments.arguments:
            if keywords and isinstance(arg, nodes.KeywordHashNode):
                args.append(ast.KeywordHash(self.hash(arg.elements)))
                continue
            if isinstance(arg, nodes.ForwardingArgumentsNode):
                # `f(...)` (Ruby 2.7): the positional and the keyword
                # arguments; the block is added by call_block().
                lineno = self.line(arg)
                args.append(ast.Splat(self.anonymous_param(arg, "*")))
                args.append(ast.KeywordHash(ast.Send(
                    ast.Hash([]), "merge",
                    [ast.HashSplat(self.anonymous_param(arg, "**"), lineno)],
                    None, lineno)))
            else:
                args.append(self.expr(arg))
        return args

    def forwards_arguments(self, arguments):
        if arguments is None:
            return False
        assert isinstance(arguments, nodes.ArgumentsNode)
        for arg in arguments.arguments:
            if isinstance(arg, nodes.ForwardingArgumentsNode):
                return True
        return False

    def call_block(self, block):
        if block is None:
            return None
        if isinstance(block, nodes.BlockArgumentNode):
            if block.expression is None:
                # `f(&)` (Ruby 3.1)
                return ast.BlockArgument(self.anonymous_param(block, "&"))
            return ast.BlockArgument(self.expr(block.expression))
        assert isinstance(block, nodes.BlockNode)
        return self.send_block(block)

    def send_block(self, node):
        lineno = self.line_at(node.opening_loc)
        self.push_block_scope()
        params = self.block_parameters(node.parameters)
        extra_stmts = self.destructuring_arguments(lineno, params)
        stmts = extra_stmts
        body = self.body(node.body)
        if isinstance(body, ast.Block):
            stmts = extra_stmts + body.stmts
        elif not isinstance(body, ast.Nil):
            stmts = extra_stmts + [self.as_statement(body)]
        block = ast.Block(stmts) if stmts else ast.Nil()
        sendblock = ast.SendBlock(
            lineno, params.args, params.splat_arg, params.post_args,
            params.kwargs, params.kwrest_arg, params.block_arg, block)
        self.save_and_pop_scope(sendblock)
        return sendblock

    def visit_block_node(self, node):
        return self.send_block(node)

    def visit_lambda_node(self, node):
        lineno = self.line_at(node.operator_loc)
        self.push_block_scope()
        params = self.block_parameters(node.parameters)
        extra_stmts = self.destructuring_arguments(lineno, params)
        stmts = extra_stmts
        body = self.body(node.body)
        if isinstance(body, ast.Block):
            stmts = extra_stmts + body.stmts
        elif not isinstance(body, ast.Nil):
            stmts = extra_stmts + [self.as_statement(body)]
        block = ast.Block(stmts) if stmts else ast.Nil()
        sendblock = ast.SendBlock(
            lineno, params.args, params.splat_arg, params.post_args,
            params.kwargs, params.kwrest_arg, params.block_arg, block)
        self.save_and_pop_scope(sendblock)
        return ast.Lambda(sendblock)

    def visit_call_node(self, node):
        name = node.name
        if node.message_loc is not None:
            lineno = self.line_at(node.message_loc)
        else:
            lineno = self.line(node)
        if node.receiver is None:
            receiver = ast.Self(lineno)
        else:
            receiver = self.expr(node.receiver)
        safe_temp = None
        safe_receiver = None
        if node.has_flag(nodes.CALL_NODE_FLAGS_SAFE_NAVIGATION):
            # `recv&.m(args)` (Ruby 2.3) is
            # `(tmp = recv).nil? ? nil : tmp.m(args)`.
            safe_temp = self.new_temp(lineno)
            safe_receiver = receiver
            receiver = ast.Variable(safe_temp, lineno)
        args = []
        if node.arguments is not None:
            # Keyword arguments are not allowed in an index (Ruby 3.4).
            takes_keywords = not (
                name == "[]" or
                node.has_flag(nodes.CALL_NODE_FLAGS_ATTRIBUTE_WRITE))
            args = self.call_args(node.arguments, keywords=takes_keywords)
        if node.has_flag(nodes.CALL_NODE_FLAGS_ATTRIBUTE_WRITE):
            if safe_temp is not None:
                raise self.unsupported(node, "&. with an assignment")
            if node.block is not None:
                raise self.unsupported(node, "a block argument in an assignment")
            # `a.b = c` and `a[b] = c` evaluate to c, not to the result of
            # calling the writer.
            if name == "[]=":
                if not args:
                    raise self.error("[]= needs a value", node)
                value = args.pop()
                return ast.Assignment(
                    ast.Subscript(receiver, args,
                                  self.line_at(node.opening_loc)),
                    value)
            assert name.endswith("=")
            end = len(name) - 1
            assert end >= 0
            if len(args) != 1:
                raise self.error("attribute assignment takes one value", node)
            return ast.Assignment(
                ast.Send(receiver, name[:end], [], None, lineno), args[0])
        block = self.call_block(node.block)
        if block is None and self.forwards_arguments(node.arguments):
            block = ast.BlockArgument(self.anonymous_param(node, "&"))
        send = ast.Send(receiver, name, args, block, lineno)
        if safe_temp is not None:
            is_nil = ast.Send(
                ast.Assignment(ast.Variable(safe_temp, lineno), safe_receiver),
                "nil?", [], None, lineno)
            return ast.If(is_nil, ast.Nil(), send)
        return send

    def visit_super_node(self, node):
        args = []
        if node.arguments is not None:
            args = self.call_args(node.arguments)
        block = self.call_block(node.block)
        if block is None and self.forwards_arguments(node.arguments):
            block = ast.BlockArgument(self.anonymous_param(node, "&"))
        return ast.Super(args, block, self.line(node))

    def visit_forwarding_super_node(self, node):
        # `super` without arguments passes on the method's own arguments,
        # also from inside a block in the method.
        lineno = self.line(node)
        method_symtable = self.symtable
        while (isinstance(method_symtable, BlockSymbolTable) and
                method_symtable.parent_symtable is not None):
            method_symtable = method_symtable.parent_symtable
        args = []
        keywords = []
        kwrest = None
        for name, tp in method_symtable.arguments:
            if tp == method_symtable.BLOCK_ARG:
                continue
            self.symtable.declare_read(name)
            arg = ast.Variable(name, lineno)
            if tp == method_symtable.SPLAT_ARG:
                args.append(ast.Splat(arg))
            elif tp == method_symtable.KEYWORD_ARG:
                keywords.append((ast.ConstantSymbol(name), arg))
            elif tp == method_symtable.KW_ARG:
                kwrest = arg
            else:
                args.append(arg)
        if keywords or kwrest is not None:
            keywords_hash = ast.Hash(keywords)
            if kwrest is not None:
                keywords_hash = ast.Send(
                    keywords_hash, "merge", [kwrest], None, lineno)
            args.append(ast.KeywordHash(keywords_hash))
        block = None
        block_node = node.block
        if block_node is not None:
            assert isinstance(block_node, nodes.BlockNode)
            block = self.send_block(block_node)
        return ast.Super(args, block, lineno)

    def visit_yield_node(self, node):
        args = []
        if node.arguments is not None:
            args = self.call_args(node.arguments)
        return ast.Yield(args, self.line(node))

    def visit_block_argument_node(self, node):
        if node.expression is None:
            return ast.BlockArgument(self.anonymous_param(node, "&"))
        return ast.BlockArgument(self.expr(node.expression))

    # Operators and control flow

    def visit_and_node(self, node):
        return ast.And(self.expr(node.left), self.expr(node.right))

    def visit_or_node(self, node):
        return ast.Or(self.expr(node.left), self.expr(node.right))

    def visit_defined_node(self, node):
        return ast.Defined(self.expr(node.value), self.line(node))

    def visit_if_node(self, node):
        if node.if_keyword_loc is None:
            # `cond ? a : b`
            subsequent = node.subsequent
            assert isinstance(subsequent, nodes.ElseNode)
            return ast.If(
                self.expr(node.predicate),
                self.ternary_branch(node.statements),
                self.ternary_branch(subsequent.statements)
            )
        return ast.If(
            self.expr(node.predicate),
            self.block(node.statements),
            self.else_clause(node.subsequent)
        )

    def ternary_branch(self, node):
        if isinstance(node, nodes.StatementsNode) and len(node.body) == 1:
            return self.expr(node.body[0])
        return self.block(node)

    def else_clause(self, node):
        if node is None:
            return ast.Nil()
        if isinstance(node, nodes.ElseNode):
            return self.block(node.statements)
        return self.expr(node)

    def visit_else_node(self, node):
        return self.block(node.statements)

    def visit_unless_node(self, node):
        return ast.If(
            self.expr(node.predicate),
            self.else_clause(node.else_clause),
            self.block(node.statements)
        )

    def visit_while_node(self, node):
        post_check = node.has_flag(nodes.LOOP_FLAGS_BEGIN_MODIFIER)
        return ast.While(
            self.expr(node.predicate), self.loop_body(node.statements, post_check),
            post_check=post_check
        )

    def visit_until_node(self, node):
        post_check = node.has_flag(nodes.LOOP_FLAGS_BEGIN_MODIFIER)
        return ast.Until(
            self.expr(node.predicate), self.loop_body(node.statements, post_check),
            post_check=post_check
        )

    def loop_body(self, statements, post_check):
        if post_check:
            # `begin ... end while cond`: prism wraps the begin block in the
            # loop's statements.
            if (isinstance(statements, nodes.StatementsNode) and
                    len(statements.body) == 1):
                begin = statements.body[0]
                if isinstance(begin, nodes.BeginNode):
                    return self.begin_body(begin)
        return self.block(statements)

    def visit_for_node(self, node):
        lineno = self.line(node)
        self.push_shared_scope()
        arg = ast.Argument("0")
        self.symtable.declare_local(arg.name)
        target = self.target(node.index)
        value = ast.Variable(arg.name, lineno)
        if isinstance(target, ast.MultiAssignable):
            asgn = ast.MultiAssignment(target, value)
        else:
            asgn = ast.Assignment(target, value)
        # The collection is evaluated outside the loop's scope.
        loop_symtable = self.symtable
        self.symtable = loop_symtable.parent_symtable
        collection = self.expr(node.collection)
        self.symtable = loop_symtable
        stmts = [ast.Statement(asgn)] + self.statement_list(node.statements)
        block = ast.SendBlock(
            lineno, [arg], None, [], [], None, None, ast.Block(stmts))
        self.save_and_pop_scope(block)
        return ast.Send(collection, "each", [], block, lineno)

    def visit_case_node(self, node):
        whens = []
        for condition in node.conditions:
            assert isinstance(condition, nodes.WhenNode)
            conds = []
            for cond in condition.conditions:
                conds.append(self.expr(cond))
            whens.append(ast.When(
                conds, self.block(condition.statements),
                self.line(condition)))
        elsebody = ast.Nil()
        else_clause = node.else_clause
        if else_clause is not None:
            assert isinstance(else_clause, nodes.ElseNode)
            elsebody = self.block(else_clause.statements)
        if node.predicate is not None:
            return ast.Case(self.expr(node.predicate), whens, elsebody)
        # A case without a subject is a chain of ifs.
        result = elsebody
        for i in range(len(whens) - 1, -1, -1):
            when = whens[i]
            cond = when.conds[0]
            for j in range(1, len(when.conds)):
                cond = ast.Or(cond, when.conds[j])
            result = ast.If(cond, when.block, result)
        return result

    def visit_return_node(self, node):
        return ast.Return(self.array_or_node(node.arguments))

    def visit_break_node(self, node):
        return ast.Break(self.array_or_node(node.arguments))

    def visit_next_node(self, node):
        return ast.Next(self.array_or_node(node.arguments))

    def visit_rescue_modifier_node(self, node):
        lineno = self.line_at(node.keyword_loc)
        return ast.TryExcept(
            self.expr(node.expression),
            [ast.ExceptHandler(
                [self.standard_error(lineno)], None,
                self.expr(node.rescue_expression)
            )],
            ast.Nil(),
            self.new_temp(lineno)
        )

    def visit_alias_method_node(self, node):
        return ast.Alias(
            self.expr(node.new_name), self.expr(node.old_name),
            self.line(node))

    def visit_undef_node(self, node):
        names = []
        for name in node.names:
            names.append(self.expr(name))
        return ast.Undef(names, self.line(node))

    # Definitions

    def declare_parameter(self, params, node):
        """Declare one required or post parameter, which may be a
        destructuring one like the `(a, b)` in `|(a, b), c|`."""
        if isinstance(node, nodes.RequiredParameterNode):
            self.symtable.declare_argument(node.name)
            return ast.Argument(node.name)
        elif isinstance(node, nodes.MultiTargetNode):
            return self.destructuring_parameter(node)
        raise self.unsupported(node, node.NAME)

    def destructuring_parameter(self, node):
        targets = []
        for child in node.lefts:
            targets.append(self.destructuring_target(child))
        rest = node.rest
        if rest is not None and not isinstance(rest, nodes.ImplicitRestNode):
            assert isinstance(rest, nodes.SplatNode)
            if rest.expression is None:
                targets.append(ast.Splat(None))
            else:
                targets.append(ast.Splat(self.destructuring_target(rest.expression)))
        for child in node.rights:
            targets.append(self.destructuring_target(child))
        return ast.MultiAssignable(targets)

    def destructuring_target(self, node):
        if isinstance(node, nodes.RequiredParameterNode):
            self.symtable.declare_local(node.name)
            return ast.Variable(node.name, -1)
        elif isinstance(node, nodes.MultiTargetNode):
            return self.destructuring_parameter(node)
        raise self.unsupported(node, node.NAME)

    def parameters(self, node):
        params = Params()
        if node is None:
            return params
        assert isinstance(node, nodes.ParametersNode)
        for param in node.requireds:
            params.args.append(self.declare_parameter(params, param))
        for param in node.optionals:
            assert isinstance(param, nodes.OptionalParameterNode)
            self.symtable.declare_argument(param.name)
            params.args.append(ast.Argument(param.name, self.expr(param.value)))
        rest = node.rest
        if isinstance(rest, nodes.RestParameterNode):
            name = rest.name
            if name is None:
                name = "*"
            self.symtable.declare_argument(name, self.symtable.SPLAT_ARG)
            params.splat_arg = name
        elif isinstance(rest, nodes.ImplicitRestNode):
            # `|a,|`
            self.symtable.declare_argument("*")
            params.splat_arg = "*"
        elif rest is not None:
            raise self.unsupported(rest, rest.NAME)
        for param in node.posts:
            params.post_args.append(self.declare_parameter(params, param))
        for param in node.keywords:
            if isinstance(param, nodes.RequiredKeywordParameterNode):
                self.symtable.declare_argument(
                    param.name, self.symtable.KEYWORD_ARG)
                params.kwargs.append(ast.Argument(param.name, None))
            else:
                assert isinstance(param, nodes.OptionalKeywordParameterNode)
                self.symtable.declare_argument(
                    param.name, self.symtable.KEYWORD_ARG)
                params.kwargs.append(
                    ast.Argument(param.name, self.expr(param.value)))
        kwrest = node.keyword_rest
        if isinstance(kwrest, nodes.KeywordRestParameterNode):
            name = kwrest.name
            if name is None:
                name = "**"
            self.symtable.declare_argument(name, self.symtable.KW_ARG)
            params.kwrest_arg = name
        elif isinstance(kwrest, nodes.ForwardingParameterNode):
            # `def f(...)` takes hidden rest, keyword rest and block
            # parameters, which `g(...)` passes on.
            self.symtable.declare_argument("*", self.symtable.SPLAT_ARG)
            params.splat_arg = "*"
            self.symtable.declare_argument("**", self.symtable.KW_ARG)
            params.kwrest_arg = "**"
            self.symtable.declare_argument("&", self.symtable.BLOCK_ARG)
            params.block_arg = "&"
        elif isinstance(kwrest, nodes.NoKeywordsParameterNode):
            pass
        elif kwrest is not None:
            raise self.unsupported(kwrest, kwrest.NAME)
        block = node.block
        if block is not None:
            assert isinstance(block, nodes.BlockParameterNode)
            name = block.name
            if name is None:
                name = "&"
            self.symtable.declare_argument(name, self.symtable.BLOCK_ARG)
            params.block_arg = name
        return params

    def block_parameters(self, node):
        if node is None:
            return Params()
        if isinstance(node, nodes.BlockParametersNode):
            params = self.parameters(node.parameters)
            for local in node.locals:
                assert isinstance(local, nodes.BlockLocalVariableNode)
                self.symtable.declare_local(local.name)
            return params
        elif isinstance(node, nodes.NumberedParametersNode):
            # `_1`, `_2`, ... (Ruby 2.7)
            params = Params()
            for i in range(1, node.maximum + 1):
                name = "_%d" % i
                self.symtable.declare_argument(name)
                params.args.append(ast.Argument(name))
            return params
        elif isinstance(node, nodes.ItParametersNode):
            # `it` (Ruby 3.4)
            params = Params()
            self.symtable.declare_argument("it")
            params.args.append(ast.Argument("it"))
            return params
        raise self.unsupported(node, node.NAME)

    def destructuring_arguments(self, lineno, params):
        """Destructuring parameters get a synthetic name, and the body
        starts by assigning them to the real targets."""
        extra_stmts = []
        idx = 0
        for arg in params.args:
            if isinstance(arg, ast.MultiAssignable):
                new_arg = ast.Argument(str(idx))
                asgn = ast.MultiAssignment(arg, ast.Variable(new_arg.name, lineno))
                params.args[idx] = new_arg
                self.symtable.declare_argument(new_arg.name)
                extra_stmts.append(ast.Statement(asgn))
            idx += 1
        offset = idx
        idx = 0
        for arg in params.post_args:
            if isinstance(arg, ast.MultiAssignable):
                new_arg = ast.Argument(str(idx + offset))
                asgn = ast.MultiAssignment(arg, ast.Variable(new_arg.name, lineno))
                params.post_args[idx] = new_arg
                self.symtable.declare_argument(new_arg.name)
                extra_stmts.append(ast.Statement(asgn))
            idx += 1
        extra_stmts.reverse()
        return extra_stmts

    def visit_def_node(self, node):
        lineno = self.line_at(node.def_keyword_loc)
        parent = None
        if node.receiver is not None:
            parent = self.expr(node.receiver)
        self.push_local_scope()
        params = self.parameters(node.parameters)
        extra_stmts = self.destructuring_arguments(lineno, params)
        body = self.body(node.body)
        if extra_stmts:
            if isinstance(body, ast.Nil):
                body = ast.Block(extra_stmts)
            elif isinstance(body, ast.Block):
                body = ast.Block(extra_stmts + body.stmts)
            else:
                body = ast.Block(extra_stmts + [self.as_statement(body)])
        function = ast.Function(
            lineno, parent, node.name, params.args, params.splat_arg,
            params.post_args, params.kwargs, params.kwrest_arg,
            params.block_arg, body)
        self.save_and_pop_scope(function)
        return function

    def module_path(self, node):
        """The scope and name of a class or module being defined."""
        if isinstance(node, nodes.ConstantReadNode):
            lineno = self.line(node)
            return ast.Scope(lineno), node.name
        elif isinstance(node, nodes.ConstantPathNode):
            scope = None
            if node.parent is not None:
                scope = self.expr(node.parent)
            return scope, self.constant_name(node.name, node)
        raise self.error("class/module name must be CONSTANT", node)

    def visit_class_node(self, node):
        scope, name = self.module_path(node.constant_path)
        superclass = None
        if node.superclass is not None:
            superclass = self.expr(node.superclass)
        self.push_local_scope()
        result = ast.Class(scope, name, superclass, self.body(node.body))
        self.save_and_pop_scope(result)
        return result

    def visit_module_node(self, node):
        scope, name = self.module_path(node.constant_path)
        self.push_local_scope()
        result = ast.Module(scope, name, self.body(node.body))
        self.save_and_pop_scope(result)
        return result

    def visit_singleton_class_node(self, node):
        value = self.expr(node.expression)
        self.push_local_scope()
        result = ast.SingletonClass(
            value, self.body(node.body), self.line(node))
        self.save_and_pop_scope(result)
        return result

    # Pattern matching (Ruby 2.7/3.0)
    #
    # A pattern becomes an expression that is truthy when the value in a
    # hidden local variable matches, binding the pattern's variables as a
    # side effect: `in [Integer => a, *]` is roughly
    # `v.respond_to?(:deconstruct) && (d = v.deconstruct; true) &&
    #  Array === d && d.length >= 1 && (e = d[0]; true) &&
    #  Integer === e && (a = e; true)`.

    def and_all(tests):
        result = tests[-1]
        for i in range(len(tests) - 2, -1, -1):
            result = ast.And(tests[i], result)
        return result
    and_all = staticmethod(and_all)

    def set_and_true(self, name, value, lineno):
        """`(name = value; true)`"""
        return ast.Block([
            ast.Statement(ast.Assignment(ast.Variable(name, lineno), value)),
            ast.Statement(ast.ConstantBool(True)),
        ])

    def send(self, receiver, name, args, lineno):
        return ast.Send(receiver, name, args, None, lineno)

    def constant(self, name, lineno):
        return ast.LookupConstant(None, name, lineno)

    def pattern_test(self, pattern, value_name):
        """An expression that is truthy if the value in the local
        `value_name` matches `pattern`."""
        lineno = self.line(pattern)
        value = ast.Variable(value_name, lineno)
        if isinstance(pattern, nodes.LocalVariableTargetNode):
            self.symtable.declare_write(pattern.name)
            return self.set_and_true(pattern.name, value, lineno)
        elif isinstance(pattern, nodes.PinnedVariableNode):
            return self.send(self.expr(pattern.variable), "===", [value], lineno)
        elif isinstance(pattern, nodes.PinnedExpressionNode):
            return self.send(
                self.expr(pattern.expression), "===", [value], lineno)
        elif isinstance(pattern, nodes.AlternationPatternNode):
            return ast.Or(
                self.pattern_test(pattern.left, value_name),
                self.pattern_test(pattern.right, value_name))
        elif isinstance(pattern, nodes.CapturePatternNode):
            target = pattern.target
            assert isinstance(target, nodes.LocalVariableTargetNode)
            test = self.pattern_test(pattern.value, value_name)
            self.symtable.declare_write(target.name)
            return ast.And(test, self.set_and_true(target.name, value, lineno))
        elif isinstance(pattern, nodes.ArrayPatternNode):
            return self.array_pattern_test(pattern, value_name)
        elif isinstance(pattern, nodes.FindPatternNode):
            return self.find_pattern_test(pattern, value_name)
        elif isinstance(pattern, nodes.HashPatternNode):
            return self.hash_pattern_test(pattern, value_name)
        elif isinstance(pattern, nodes.ImplicitNode):
            return self.pattern_test(pattern.value, value_name)
        # A value pattern: a literal, constant, range, regexp, lambda, ...
        return self.send(self.expr(pattern), "===", [value], lineno)

    def element_test(self, pattern, value, lineno):
        """Match `pattern` against the value of the expression `value`."""
        if isinstance(pattern, nodes.LocalVariableTargetNode):
            self.symtable.declare_write(pattern.name)
            return self.set_and_true(pattern.name, value, lineno)
        temp = self.new_temp(lineno)
        return ast.And(
            self.set_and_true(temp, value, lineno),
            self.pattern_test(pattern, temp))

    def deconstruct_tests(self, constant, value_name, lineno):
        """The tests an array or find pattern starts with; returns them and
        the local holding the deconstructed array."""
        value = ast.Variable(value_name, lineno)
        tests = []
        if constant is not None:
            tests.append(self.send(self.expr(constant), "===", [value], lineno))
        tests.append(self.send(
            value, "respond_to?", [ast.ConstantSymbol("deconstruct")], lineno))
        array = self.new_temp(lineno)
        tests.append(self.set_and_true(
            array, self.send(value, "deconstruct", [], lineno), lineno))
        tests.append(self.send(
            self.constant("Array", lineno), "===",
            [ast.Variable(array, lineno)], lineno))
        return tests, array

    def array_pattern_test(self, pattern, value_name):
        lineno = self.line(pattern)
        tests, array = self.deconstruct_tests(
            pattern.constant, value_name, lineno)
        nrequired = len(pattern.requireds)
        npost = len(pattern.posts)
        length = self.send(ast.Variable(array, lineno), "length", [], lineno)
        rest = pattern.rest
        if rest is None:
            tests.append(self.send(
                length, "==", [ast.ConstantInt(nrequired + npost)], lineno))
        else:
            tests.append(self.send(
                length, ">=", [ast.ConstantInt(nrequired + npost)], lineno))
        for i in range(nrequired):
            tests.append(self.element_test(
                pattern.requireds[i],
                self.send(ast.Variable(array, lineno), "[]",
                          [ast.ConstantInt(i)], lineno),
                lineno))
        if isinstance(rest, nodes.SplatNode) and rest.expression is not None:
            rest_length = self.send(
                self.send(ast.Variable(array, lineno), "length", [], lineno),
                "-", [ast.ConstantInt(nrequired + npost)], lineno)
            tests.append(self.element_test(
                rest.expression,
                self.send(ast.Variable(array, lineno), "[]",
                          [ast.ConstantInt(nrequired), rest_length], lineno),
                lineno))
        for j in range(npost):
            index = self.send(
                self.send(ast.Variable(array, lineno), "length", [], lineno),
                "-", [ast.ConstantInt(npost - j)], lineno)
            tests.append(self.element_test(
                pattern.posts[j],
                self.send(ast.Variable(array, lineno), "[]", [index], lineno),
                lineno))
        return self.and_all(tests)

    def find_pattern_test(self, pattern, value_name):
        """`[*pre, a, b, *post]` tries every position in the array."""
        lineno = self.line(pattern)
        tests, array = self.deconstruct_tests(
            pattern.constant, value_name, lineno)
        n = len(pattern.requireds)
        found = self.new_temp(lineno)
        index = self.new_temp(lineno)
        element_tests = []
        for i in range(n):
            element_tests.append(self.element_test(
                pattern.requireds[i],
                self.send(ast.Variable(array, lineno), "[]", [
                    self.send(ast.Variable(index, lineno), "+", [ast.ConstantInt(i)], lineno)
                ], lineno),
                lineno))
        last_start = self.send(
            self.send(ast.Variable(array, lineno), "length", [], lineno), "-",
            [ast.ConstantInt(n)], lineno)
        loop = ast.While(
            ast.And(
                self.send(ast.Variable(found, lineno), "!", [], lineno),
                self.send(ast.Variable(index, lineno), "<=", [last_start], lineno)),
            ast.Block([ast.Statement(ast.If(
                self.and_all(element_tests),
                ast.Block([ast.Statement(ast.Assignment(
                    ast.Variable(found, lineno), ast.ConstantBool(True)))]),
                ast.Block([ast.Statement(ast.Assignment(
                    ast.Variable(index, lineno), self.send(ast.Variable(index, lineno), "+", [ast.ConstantInt(1)], lineno)))]),
            ))])
        )
        tests.append(ast.Block([
            ast.Statement(ast.Assignment(
                ast.Variable(found, lineno), ast.ConstantBool(False))),
            ast.Statement(ast.Assignment(ast.Variable(index, lineno), ast.ConstantInt(0))),
            ast.Statement(loop),
            ast.Statement(ast.Variable(found, lineno)),
        ]))
        left = pattern.left
        if isinstance(left, nodes.SplatNode) and left.expression is not None:
            tests.append(self.element_test(
                left.expression,
                self.send(ast.Variable(array, lineno), "[]", [ast.ConstantInt(0), ast.Variable(index, lineno)], lineno),
                lineno))
        right = pattern.right
        if isinstance(right, nodes.SplatNode) and right.expression is not None:
            after = self.send(ast.Variable(index, lineno), "+", [ast.ConstantInt(n)], lineno)
            tests.append(self.element_test(
                right.expression,
                self.send(ast.Variable(array, lineno), "[]", [
                    ast.Range(after, ast.Nil(), False)
                ], lineno),
                lineno))
        return self.and_all(tests)

    def hash_pattern_test(self, pattern, value_name):
        lineno = self.line(pattern)
        value = ast.Variable(value_name, lineno)
        tests = []
        if pattern.constant is not None:
            tests.append(self.send(
                self.expr(pattern.constant), "===", [value], lineno))
        tests.append(self.send(
            value, "respond_to?", [ast.ConstantSymbol("deconstruct_keys")],
            lineno))
        keys = []
        for element in pattern.elements:
            assert isinstance(element, nodes.AssocNode)
            key = element.key
            if not isinstance(key, nodes.SymbolNode):
                raise self.unsupported(element, "a non-symbol key in a hash pattern")
            keys.append(ast.ConstantSymbol(key.unescaped))
        rest = pattern.rest
        if isinstance(rest, nodes.AssocSplatNode) and rest.value is not None:
            # With `**rest` every key is wanted.
            wanted = ast.Nil()
        else:
            wanted = ast.Array(keys)
        hash = self.new_temp(lineno)
        tests.append(self.set_and_true(
            hash, self.send(value, "deconstruct_keys", [wanted], lineno),
            lineno))
        tests.append(self.send(
            self.constant("Hash", lineno), "===", [ast.Variable(hash, lineno)], lineno))
        for element in pattern.elements:
            assert isinstance(element, nodes.AssocNode)
            key = element.key
            assert isinstance(key, nodes.SymbolNode)
            name = key.unescaped
            tests.append(self.send(
                ast.Variable(hash, lineno), "key?", [ast.ConstantSymbol(name)], lineno))
            tests.append(self.element_test(
                element.value,
                self.send(ast.Variable(hash, lineno), "[]", [ast.ConstantSymbol(name)], lineno),
                lineno))
        remaining = self.send(ast.Variable(hash, lineno), "except", list(keys), lineno)
        if isinstance(rest, nodes.AssocSplatNode):
            if rest.value is not None:
                tests.append(self.element_test(rest.value, remaining, lineno))
        elif isinstance(rest, nodes.NoKeywordsParameterNode):
            # `**nil`: no other keys allowed.
            tests.append(self.send(remaining, "empty?", [], lineno))
        elif not pattern.elements:
            # `in {}` only matches an empty hash.
            tests.append(self.send(ast.Variable(hash, lineno), "empty?", [], lineno))
        return self.and_all(tests)

    def in_clause_test(self, pattern, value_name):
        """The test for one `in` clause, including its guard."""
        if isinstance(pattern, nodes.IfNode) or isinstance(pattern, nodes.UnlessNode):
            if isinstance(pattern, nodes.IfNode):
                guard = pattern.predicate
                statements = pattern.statements
            else:
                assert isinstance(pattern, nodes.UnlessNode)
                guard = pattern.predicate
                statements = pattern.statements
            assert isinstance(statements, nodes.StatementsNode)
            test = self.pattern_test(statements.body[0], value_name)
            guard_test = self.expr(guard)
            if isinstance(pattern, nodes.UnlessNode):
                guard_test = self.send(guard_test, "!", [], self.line(pattern))
            return ast.And(test, guard_test)
        return self.pattern_test(pattern, value_name)

    def value_pattern_expr(self, pattern):
        """For a pattern that is matched with a single `===` (the last one
        tried, for an alternation), the expression on the left of it."""
        while isinstance(pattern, nodes.AlternationPatternNode):
            pattern = pattern.right
        if isinstance(pattern, nodes.PinnedVariableNode):
            return self.expr(pattern.variable)
        elif isinstance(pattern, nodes.PinnedExpressionNode):
            return self.expr(pattern.expression)
        elif (isinstance(pattern, nodes.LocalVariableTargetNode) or
              isinstance(pattern, nodes.ArrayPatternNode) or
              isinstance(pattern, nodes.FindPatternNode) or
              isinstance(pattern, nodes.HashPatternNode) or
              isinstance(pattern, nodes.CapturePatternNode) or
              isinstance(pattern, nodes.ImplicitNode) or
              isinstance(pattern, nodes.IfNode) or
              isinstance(pattern, nodes.UnlessNode)):
            return None
        return self.expr(pattern)

    def no_match_error(self, value_name, lineno, pattern):
        """`raise NoMatchingPatternError`, with Ruby's message for a value
        pattern: "5: String === 5 does not return true"."""
        inspected = self.send(ast.Variable(value_name, lineno), "inspect", [], lineno)
        message = inspected
        if pattern is not None:
            expr = self.value_pattern_expr(pattern)
            if expr is not None:
                message = ast.DynamicString([
                    inspected, ast.ConstantString(": "),
                    self.send(expr, "inspect", [], lineno),
                    ast.ConstantString(" === "),
                    self.send(ast.Variable(value_name, lineno), "inspect", [], lineno),
                    ast.ConstantString(" does not return true"),
                ])
        return self.send(ast.Self(lineno), "raise", [
            self.constant("NoMatchingPatternError", lineno), message,
        ], lineno)

    def visit_case_match_node(self, node):
        lineno = self.line(node)
        value_name = self.new_temp(lineno)
        else_clause = node.else_clause
        if else_clause is not None:
            assert isinstance(else_clause, nodes.ElseNode)
            result = self.block(else_clause.statements)
        else:
            last_pattern = None
            if node.conditions:
                last = node.conditions[len(node.conditions) - 1]
                assert isinstance(last, nodes.InNode)
                last_pattern = last.pattern
            result = self.no_match_error(value_name, lineno, last_pattern)
        tests = []
        bodies = []
        for condition in node.conditions:
            assert isinstance(condition, nodes.InNode)
            tests.append(self.in_clause_test(condition.pattern, value_name))
            bodies.append(self.block(condition.statements))
        for i in range(len(tests) - 1, -1, -1):
            result = ast.If(tests[i], bodies[i], result)
        return ast.Block([
            ast.Statement(ast.Assignment(
                ast.Variable(value_name, lineno), self.expr(node.predicate))),
            self.as_statement(result),
        ])

    def visit_match_predicate_node(self, node):
        # `value in pattern`
        lineno = self.line(node)
        value_name = self.new_temp(lineno)
        return ast.Block([
            ast.Statement(ast.Assignment(
                ast.Variable(value_name, lineno), self.expr(node.value))),
            ast.Statement(ast.If(
                self.pattern_test(node.pattern, value_name),
                ast.ConstantBool(True), ast.ConstantBool(False))),
        ])

    def visit_match_required_node(self, node):
        # `value => pattern`
        lineno = self.line(node)
        value_name = self.new_temp(lineno)
        return ast.Block([
            ast.Statement(ast.Assignment(
                ast.Variable(value_name, lineno), self.expr(node.value))),
            ast.Statement(ast.If(
                self.pattern_test(node.pattern, value_name),
                ast.Nil(),
                self.no_match_error(value_name, lineno, node.pattern))),
        ])

    # Not (yet) supported, but with a better message than the default.

    def visit_redo_node(self, node):
        return ast.Redo(self.line(node))

    def visit_retry_node(self, node):
        return ast.Retry(self.line(node))

    def visit_flip_flop_node(self, node):
        raise self.unsupported(node, "flip-flop")

    def visit_pre_execution_node(self, node):
        raise self.unsupported(node, "BEGIN")

    def visit_post_execution_node(self, node):
        raise self.unsupported(node, "END")

    def visit_alias_global_variable_node(self, node):
        # alias $new $old: Topaz.alias_global(:$new, :$old)
        lineno = self.line(node)
        names = []
        for name_node in [node.new_name, node.old_name]:
            name = getattr(name_node, "name", None)
            if name is None:
                raise self.unsupported(node, "aliasing this global variable")
            names.append(ast.ConstantSymbol(name))
        return ast.Send(
            ast.LookupConstant(None, "Topaz", lineno), "alias_global", names, None, lineno)

    def visit_source_encoding_node(self, node):
        # Source files are UTF-8.
        lineno = self.line(node)
        return ast.LookupConstant(
            ast.LookupConstant(None, "Encoding", lineno), "UTF_8", lineno)

    def visit_match_write_node(self, node):
        # `/(?<name>...)/ =~ string` also assigns each named capture to a
        # local variable, or nil if there was no match.
        lineno = self.line(node)
        result = self.new_temp(lineno)
        stmts = [ast.Statement(ast.Assignment(
            ast.Variable(result, lineno), self.expr(node.call)))]
        for target in node.targets:
            assert isinstance(target, nodes.LocalVariableTargetNode)
            self.symtable.declare_write(target.name)
            match = ast.Global("$~")
            capture = ast.If(
                match,
                ast.Send(ast.Global("$~"), "[]",
                         [ast.ConstantSymbol(target.name)], None, lineno),
                ast.Nil())
            stmts.append(ast.Statement(ast.Assignment(
                ast.Variable(target.name, lineno), capture)))
        stmts.append(ast.Statement(ast.Variable(result, lineno)))
        return ast.Block(stmts)
