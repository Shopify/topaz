import pytest

from rpython.rlib.rarithmetic import LONG_BIT

from topaz.objects.codeobject import W_CodeObject
from tests.base import BaseTopazTest


def method_code(space, parameters):
    code = space.compile('def f(%s); nil; end' % parameters, None)
    return next(w for w in code.consts_w if isinstance(w, W_CodeObject))


@pytest.mark.parametrize('parameters, extra', [
    ('', 0), ('a, *rest, **kw', 0), ('a:', 0), ('a: 1', 1),
    ('a: 1, b: 2, **rest', 1)])
def test_frame_layout(space, parameters, extra):
    code = method_code(space, parameters)
    frame = space.create_frame(code)
    assert not hasattr(frame, 'kwargs_given')
    assert len(frame.localsstack_w) == (
        2 * len(code.cellvars) + len(code.freevars) + code.max_stackdepth + extra)


def test_omitted_keywords_do_not_box(space, monkeypatch):
    code = method_code(space, 'a: 1, b: 2')
    frame = space.create_frame(code)

    def unexpected_box(value):
        raise AssertionError('boxed an empty keyword bitmap')

    monkeypatch.setattr(space, 'newint', unexpected_box)
    frame.handle_args(space, code, [], None)
    assert frame.localsstack_w[-1] is None
    assert not frame.is_kwarg_given(space, 0)
    assert not frame.is_kwarg_given(space, 1)


def test_given_keywords_box_once_and_use_highest_bit(space, monkeypatch):
    code = method_code(space, ', '.join('k%d: 0' % i for i in range(LONG_BIT)))
    frame = space.create_frame(code)
    keywords = space.newhash()
    keywords.is_keywords = True
    for i in (0, LONG_BIT - 1):
        keywords.setitem(space.newsymbol('k%d' % i), space.w_nil)
    boxes = []
    newint = space.newint

    def record(value):
        boxes.append(value)
        return newint(value)

    monkeypatch.setattr(space, 'newint', record)
    frame.handle_args(space, code, [keywords], None)
    assert boxes == [-(1 << (LONG_BIT - 1)) + 1]
    assert frame.is_kwarg_given(space, 0)
    assert frame.is_kwarg_given(space, LONG_BIT - 1)
    assert not frame.is_kwarg_given(space, 1)


class TestKeywordSlots(BaseTopazTest):
    @pytest.mark.parametrize('count', [LONG_BIT - 1, LONG_BIT])
    def test_bitmap_boundary(self, space, count):
        parameters = ', '.join('k%d: %d' % (i, i) for i in range(count))
        source = '''
          def f(%s); [k0, k%d]; end
          return [f, f(k0: nil, k%d: false)]
        ''' % (parameters, count - 1, count - 1)
        assert self.unwrap(space, space.execute(source)) == [
            [0, count - 1], [None, False]]

    @pytest.mark.parametrize('template', [
        'def f(%s); end', '->(%s) {}', 'proc { |%s| }',
        'Object.send(:define_method, :f) { |%s| }'])
    def test_too_many_defaults_is_ruby_syntax_error(self, space, template):
        parameters = ', '.join('k%d: 0' % i for i in range(LONG_BIT + 1))
        source = template % parameters
        message = 'too many keyword arguments with defaults (maximum %d)' % LONG_BIT
        with self.raises(space, 'SyntaxError', message):
            space.execute(source)

    def test_limit_does_not_count_required_keywords(self, space):
        count = LONG_BIT + 1
        parameters = ', '.join('k%d:' % i for i in range(count))
        arguments = ', '.join('k%d: %d' % (i, i) for i in range(count))
        source = 'def f(%s, optional: 7); [k%d, optional]; end; return f(%s)' % (
            parameters, count - 1, arguments)
        assert self.unwrap(space, space.execute(source)) == [count - 1, 7]

    def test_default_assignment_does_not_change_given_bits(self, space):
        source = '''
          def f(a: binding.local_variable_set(:b, 9), b: 2)
            [a, b]
          end
          return [f, f(b: nil), f(a: false)]
        '''
        assert self.unwrap(space, space.execute(source)) == [[9, 2], [9, 9], [False, 2]]

    def test_slot_is_not_visible_in_binding_or_captured_cells(self, space):
        source = '''
          def f(a = 3, k: 4, **rest)
            p = proc { [a, k, rest] }
            [binding.local_variables, p]
          end
          names, p = f(k: nil, other: 5)
          return [names.sort, p.call]
        '''
        result = self.unwrap(space, space.execute(source))
        assert result == [
            ['a', 'k', 'p', 'rest'], [3, None, {'other': 5}]], result

    def test_keyword_slot_after_free_variable_cells(self, space):
        source = '''
          captured = 7
          p = proc { |k: captured| [captured, k] }
          l = ->(k: captured) { [captured, k] }
          Object.send(:define_method, :f) { |k: captured| [captured, k] }
          def forward(target, **keywords)
            target.call(**keywords)
          end
          captured = 9
          return [p.call, forward(l, k: 11), l.call, l.call(k: false),
                  f, f(k: 3)]
        '''
        result = self.unwrap(space, space.execute(source))
        assert result == [
            [9, 9], [9, 11], [9, 9], [9, False], [9, 9], [9, 3]], result
