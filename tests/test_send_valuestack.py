import pytest

from topaz.error import RubyError
from .base import BaseTopazTest


def make_caller(space, args_w):
    bc = space.compile("return [1, 2, 3, 4, 5, 6]", "caller.rb")
    caller = space.create_frame(bc)
    caller.push(space.w_true)  # An unrelated value below the call.
    finaldepth = caller.stackpos
    caller.push(space.w_top_self)
    for w_arg in args_w:
        caller.push(w_arg)
    return caller, finaldepth, caller.stackpos


def assert_clean(caller, finaldepth, olddepth, space):
    assert caller.stackpos == finaldepth
    assert caller.peek() is space.w_true
    assert caller.localsstack_w[finaldepth:olddepth] == [None] * (olddepth - finaldepth)


class TestSendValueStack(BaseTopazTest):
    @pytest.mark.parametrize("source, args, expected", [
        ("def f; 42; end", [], 42),
        ("def f(a, b); [b, a]; end", [3, 7], [7, 3]),
        ("def f(a); proc { a }; end", [9], 9),
    ])
    def test_fast_call_without_argument_list(self, space, monkeypatch, source, args, expected):
        space.execute(source)
        caller, depth, olddepth = make_caller(space, [space.newint(a) for a in args])

        def no_list(n):
            raise AssertionError("fast call built an argument list")
        monkeypatch.setattr(caller, "popitemsreverse", no_list)
        execute = space.execute_frame

        def execute_checked(frame, bc, entry_pc=0):
            assert_clean(caller, depth, olddepth, space)
            return execute(frame, bc, entry_pc)
        monkeypatch.setattr(space, "execute_frame", execute_checked)
        result = space.send_valuestack("f", len(args), caller)
        if "proc" in source:
            result = space.invoke_block(result, [])
        assert self.unwrap(space, result) == expected
        assert_clean(caller, depth, olddepth, space)

    @pytest.mark.parametrize("source, name, args, expected", [
        ("def f(a=4); a; end", "f", [], 4),
        ("def f(*a); a; end", "f", [2, 3], [2, 3]),
        ("def f(&b); b; end", "f", [], None),
        ("def f(a: 5); a; end", "f", [], 5),
        ("def method_missing(n, a); a; end", "absent", [8], 8),
        ("", "nil?", [], False),
    ])
    def test_fallback_cleans_before_dispatch(self, space, monkeypatch, source, name, args, expected):
        space.execute(source)
        caller, depth, olddepth = make_caller(space, [space.newint(a) for a in args])
        send_raw = space._send_raw

        def send_checked(name, method, receiver, cls, args_w, block):
            assert_clean(caller, depth, olddepth, space)
            return send_raw(name, method, receiver, cls, args_w, block)
        monkeypatch.setattr(space, "_send_raw", send_checked)
        result = space.send_valuestack(name, len(args), caller)
        assert self.unwrap(space, result) == expected

    def test_empty_keyword_hash_uses_argument_parser(self, space):
        space.execute("def f(a); a; end")
        w_keywords = space.newhash()
        w_keywords.is_keywords = True
        caller, depth, olddepth = make_caller(space, [w_keywords])
        with self.raises(space, "ArgumentError", "wrong number of arguments (given 0, expected 1)"):
            space.send_valuestack("f", 1, caller)
        assert_clean(caller, depth, olddepth, space)

    @pytest.mark.parametrize("source, args", [
        ("def f(a); a; end", []),
        ("def f; raise 'failure'; end", []),
    ])
    def test_call_error_keeps_caller_clean(self, space, source, args):
        space.execute(source)
        caller, depth, olddepth = make_caller(space, args)
        with pytest.raises(RubyError):
            space.send_valuestack("f", len(args), caller)
        assert_clean(caller, depth, olddepth, space)

    @pytest.mark.parametrize("failure_point", ["lookup", "setup"])
    def test_preparation_error_keeps_caller_clean(self, space, monkeypatch, failure_point):
        space.execute("def f(a); a; end")
        caller, depth, olddepth = make_caller(space, [space.newint(1)])

        def fail(*args, **kwargs):
            raise ValueError("preparation failed")
        if failure_point == "lookup":
            monkeypatch.setattr(space.getclass(space.w_top_self), "find_method", fail)
        else:
            monkeypatch.setattr(space, "create_frame", fail)
        with pytest.raises(ValueError):
            space.send_valuestack("f", 1, caller)
        assert_clean(caller, depth, olddepth, space)
