import pytest

from topaz.frame import BuiltinFrame
from topaz.objects.functionobject import W_FunctionObject


@pytest.mark.parametrize("entry_pc", [0, 1, 255, 1 << 30])
def test_packed_frame_flags_are_independent(space, entry_pc):
    frame = space.create_frame(space.compile("nil", "test_frame.rb"))
    assert frame.get_entry_pc() == 0
    assert frame.get_visibility() == W_FunctionObject.PUBLIC
    assert not frame.is_escaped()

    for visibility in (W_FunctionObject.PRIVATE, W_FunctionObject.PROTECTED,
                       W_FunctionObject.MODULE_FUNCTION, W_FunctionObject.PUBLIC):
        frame.set_entry_pc(entry_pc)
        frame.set_escaped(True)
        frame.set_visibility(visibility)
        assert frame.get_entry_pc() == entry_pc
        assert frame.is_escaped()
        assert frame.get_visibility() == visibility

        frame.set_entry_pc(0)
        assert frame.is_escaped()
        assert frame.get_visibility() == visibility
        frame.set_entry_pc(entry_pc)
        frame.set_escaped(False)
        assert frame.get_entry_pc() == entry_pc
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
