from StringIO import StringIO

from topaz import consts
from topaz.objects.codeobject import UnwindHandler, UnwindInterval


def dis(code, depth=None):
    output = StringIO()
    assert code.dis(file=output, depth=depth) is None
    return output.getvalue()


def test_stdout_and_operands(space, capsys):
    code = space.compile('1 + 2', None)
    code.dis()
    output, error = capsys.readouterr()
    assert not error
    assert output == dis(code)
    assert output == (
        '  1       0 LOAD_CONST               0 (1)\n'
        '          3 LOAD_CONST               1 (2)\n'
        '          6 SEND                     2, 1 (:+)\n'
        '         11 RETURN\n')


def test_exception_table_variable_width_and_parent_only_handler(space):
    code = space.compile('1', None)
    # Inner rescue covers LOAD_CONST (three bytes); its parent has no
    # interval of its own, but must still be visible in the dump.
    code.unwind_handlers = [UnwindHandler(UnwindHandler.ENSURE, 3, -1, 0),
                            UnwindHandler(UnwindHandler.RESCUE, 3, 0, 0)]
    code.unwind_intervals = [UnwindInterval(0, 3, 1)]
    output = dis(code)
    assert '    >>    3 RETURN\n' in output
    assert output.endswith(
        'ExceptionTable:\n'
        '  0 to 0 -> 3 [0] rescue handler=1 parent=0\n'
        'Handlers:\n'
        '  0: ensure -> 3 [0] parent=-1\n'
        '  1: rescue -> 3 [0] parent=0\n')


def test_large_operand_and_jump_target(space):
    code = space.compile('1', None)
    code.code = chr(consts.JUMP) + '\x03\x01' + chr(consts.LOAD_SELF) * 256 + chr(consts.RETURN)
    code.lineno_table = [1] * len(code.code)
    output = dis(code)
    assert '0 JUMP                     259 (to 259)' in output
    assert '    >>  259 RETURN' in output


def test_nested_code_lines_cells_keywords_and_depth(space):
    code = space.compile('def f(x = 1, y: 2)\n  [x, y].each { x }\nend', None)
    output = dis(code)
    assert 'Disassembly of <code f,' in output
    assert 'JUMP_IF_KWARG_GIVEN' in output
    assert 'keyword y)' in output
    assert '(x)' in output
    assert '(y)' in output
    assert '\n\n  2 ' in output
    assert output.count('Disassembly of ') == 2
    assert dis(code, depth=1).count('Disassembly of ') == 1
    assert 'Disassembly of ' not in dis(code, depth=0)


def test_ruby_literals_and_unwind_annotations(space):
    code = space.compile('begin; [nil, true, false, "hi", 1.5, 100000000000000000000]; ensure; 2; end', None)
    output = dis(code)
    # String literals are stored as symbols and converted at runtime.
    for literal in ('nil', 'true', 'false', ':hi', '1.5', '100000000000000000000'):
        assert '(' + literal + ')' in output, (literal, output)
    assert '(resume handler -1)' in output
    assert 'ensure handler=0 parent=-1' in output


def test_escaped_constants(space):
    from topaz.utils.disassembler import constant_repr
    assert constant_repr(space.newstr_fromstr('a\nb')) == '"a\\nb"'
    assert constant_repr(space.newsymbol('a\nb')) == ':"a\\nb"'


def test_loop_and_nested_rescue(space):
    code = space.compile('while true; begin; 1; rescue RuntimeError; break; end; end', None)
    output = dis(code)
    assert 'loop handler=0 parent=-1' in output
    assert 'rescue handler=1 parent=0' in output
    assert '(resume handler 0)' in output
