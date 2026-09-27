def t; yield; rescue NameError, ArgumentError, TypeError => e; e.message; end
out = []
out << t { nil.foo } << t { 1.foo } << t { Object.foo } << t { Kernel.foo }
out << t { Integer.instance_method(:nope) }
def two(a, b = 1) = a
out << t { two } << t { two(1, 2, 3) }
out << t { [1, 2].first("x") }
p out
