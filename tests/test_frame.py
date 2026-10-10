import pytest

from topaz.frame import BuiltinFrame
from topaz.objects.functionobject import W_FunctionObject


@pytest.mark.parametrize("back_pc", [0, 1, 255, 1 << 30])
def test_packed_frame_flags_are_independent(space, back_pc):
    frame = space.create_frame(space.compile("nil", "test_frame.rb"))
    assert frame.get_back_pc() == 0
    assert frame.get_visibility() == W_FunctionObject.PUBLIC
    assert not frame.is_escaped()

    for visibility in (W_FunctionObject.PRIVATE, W_FunctionObject.PROTECTED,
                       W_FunctionObject.MODULE_FUNCTION, W_FunctionObject.PUBLIC):
        frame.set_back_pc(back_pc)
        frame.set_escaped(True)
        frame.set_visibility(visibility)
        assert frame.get_back_pc() == back_pc
        assert frame.is_escaped()
        assert frame.get_visibility() == visibility

        frame.set_back_pc(0)
        assert frame.is_escaped()
        assert frame.get_visibility() == visibility
        frame.set_back_pc(back_pc)
        frame.set_escaped(False)
        assert frame.get_back_pc() == back_pc
        assert frame.get_visibility() == visibility
        assert not frame.is_escaped()


def test_builtin_frame_escape_flag():
    frame = BuiltinFrame("test")
    assert not frame.is_escaped()
    frame.set_escaped(True)
    assert frame.is_escaped()
    frame.set_escaped(False)
    assert not frame.is_escaped()


def test_unused_regexp_cell_is_not_allocated(space):
    bc = space.compile("return 42", "test_frame.rb")
    frame = space.create_frame(bc)
    assert frame.regexp_match_cell is None
    with space.getexecutioncontext().visit_frame(frame):
        assert space.int_w(space.execute_frame(frame, bc)) == 42
    assert frame.regexp_match_cell is None


@pytest.mark.parametrize('supplied', [0, 1, 2])
@pytest.mark.parametrize('enter_first', [False, True])
def test_argument_entry_pc_does_not_overwrite_caller_pc(space, supplied, enter_first):
    from tests.test_keyword_slots import method_code
    code = method_code(space, 'a = 1, b = 2')
    frame = space.create_frame(code)
    ec = space.getexecutioncontext()
    ec.last_instr = 123
    args_w = [space.newint(i) for i in range(supplied)]
    if enter_first:
        with ec.visit_frame(frame):
            entry_pc = frame.handle_args(space, code, args_w, None)
            assert frame.get_back_pc() == 123
    else:
        entry_pc = frame.handle_args(space, code, args_w, None)
        with ec.visit_frame(frame):
            assert frame.get_back_pc() == 123
    assert entry_pc == code.default_entry_pcs[supplied]


def test_builtin_caller_pc_preserves_escape_flag():
    frame = BuiltinFrame('test')
    frame.set_escaped(True)
    frame.set_back_pc(12345)
    assert frame.get_back_pc() == 12345
    assert frame.is_escaped()
    frame.set_escaped(False)
    assert frame.get_back_pc() == 12345
