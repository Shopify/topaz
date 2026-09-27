from topaz.prism import binding, nodes


def load(source, scopes=None):
    serialized = binding.serialize_parse(
        source, binding.serialize_options("t.rb", 1, scopes or []))
    loader = nodes.Loader(source, serialized)
    return loader, loader.load()


class TestPrismLoader(object):
    def test_program(self):
        loader, program = load("x = 1\nputs x + 2**70, 1.5, :sym, 'str'\n")
        assert isinstance(program, nodes.ProgramNode)
        assert program.locals == ["x"]
        [write, call] = program.statements.body
        assert isinstance(write, nodes.LocalVariableWriteNode)
        assert write.name == "x"
        assert write.value.value.toint() == 1
        assert isinstance(call, nodes.CallNode)
        assert call.name == "puts"
        assert call.has_flag(nodes.CALL_NODE_FLAGS_IGNORE_VISIBILITY)
        [plus, flt, sym, string] = call.arguments.arguments
        assert plus.name == "+"
        assert isinstance(plus.receiver, nodes.LocalVariableReadNode)
        [pow] = plus.arguments.arguments
        assert pow.arguments.arguments[0].value.toint() == 70
        assert flt.value == 1.5
        assert sym.unescaped == "sym"
        assert string.unescaped == "str"
        assert loader.line_of(call.location.start) == 2
        assert loader.errors == []

    def test_def_node(self):
        # DefNodes carry an extra length prefix in the serialization.
        loader, program = load("def f(a, b = 1, *c, d:, **e, &f) = a\nf(1)\n")
        [defn, call] = program.statements.body
        assert isinstance(defn, nodes.DefNode)
        assert defn.name == "f"
        assert defn.locals == ["a", "b", "c", "d", "e", "f"]
        params = defn.parameters
        assert [p.name for p in params.requireds] == ["a"]
        assert params.rest.name == "c"
        assert params.keyword_rest.name == "e"
        assert call.name == "f"

    def test_scopes(self):
        # As for eval: the program runs in the innermost scope given, so its
        # locals are visible at depth 0.
        _, program = load("x; y", [binding.Scope(["x"])])
        [read, call] = program.statements.body
        assert isinstance(read, nodes.LocalVariableReadNode)
        assert read.depth == 0
        assert isinstance(call, nodes.CallNode)

    def test_ruby_4_syntax(self):
        _, program = load("[1].map { it * 2 }\nx = 1\n  || 2\n")
        [call, write] = program.statements.body
        assert isinstance(call.block.parameters, nodes.ItParametersNode)
        assert isinstance(write.value, nodes.OrNode)

    def test_syntax_error(self):
        loader, _ = load("def f(\n")
        assert loader.errors
        assert loader.line_of(loader.errors[0].location.start) >= 1
