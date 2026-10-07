def bar(a, b) = a + b
def foo(...) = bar(...)
300_000_000.times { foo(1, 2) }
p foo(3, 4)
