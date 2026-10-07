from topaz.prism import binding, nodes


def load(source, scopes=None):
    serialized = binding.serialize_parse(
        source, binding.serialize_options("t.rb", 1, scopes or []))
    loader = nodes.Loader(source, serialized)
    return loader, loader.load()


class TestPrismLoader(object):
    def test_integer_words(self):
        def varuint(value):
            result = []
            while value >= 128:
                result.append(chr((value & 127) | 128))
                value >>= 7
            result.append(chr(value))
            return ''.join(result)

        values = [0L, 1L, 0xffffffffL, 0x100000000L,
                  0x0123456789abcdefL, (1L << 4096) + 1]
        for bit in [31, 32, 62, 63, 64, 93, 126, 127, 128]:
            values.extend([(1L << bit) - 1, 1L << bit, (1L << bit) + 1])
        for value in values:
            words = []
            remaining = value
            while remaining:
                words.append(remaining & 0xffffffff)
                remaining >>= 32
            # Also exercise explicit zero words and leading zero padding.
            for padded in [words, words + [0]]:
                for negative in [False, True]:
                    data = (chr(int(negative)) + varuint(len(padded)) +
                            ''.join(varuint(word) for word in padded))
                    loader = nodes.Loader('', data + '!')
                    result = loader.load_integer()
                    assert result.tolong() == (-value if negative else value)
                    assert loader.pos == len(data)
                    assert loader.load_byte() == ord('!')

    def test_large_integer_literal(self):
        value = (1L << 4096) + (1L << 63) + 0xffffffff
        loader, program = load(str(value))
        [integer] = program.statements.body
        assert isinstance(integer, nodes.IntegerNode)
        assert integer.value.tolong() == value
        assert loader.errors == []

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
