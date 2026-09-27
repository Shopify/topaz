out = []
def g(a, k: 1) = [a, k]
def h(**kw) = kw
def pos(x) = x
def any(*args) = args
out << g({k: 2}) << g(1, k: 3) << g(1, **{k: 4}) << h(a: 1) << pos(a: 1) << any(a: 1) << any(**{}) << any(*[], **{})
begin; g(1, {k: 2}); rescue ArgumentError => e; out << e.message; end
begin; h({a: 1}); rescue ArgumentError => e; out << e.message; end
class Target; def call(a, b: 0) = [a, b]; end
class Proxy
  def initialize(t) = @t = t
  def method_missing(name, *args, &blk) = @t.send(name, *args, &blk)
  ruby2_keywords :method_missing
end
out << Proxy.new(Target.new).call(1, b: 2)
def fwd(...) = g(...)
out << fwd(5, k: 6) << fwd({k: 7})
out << [1, 2].each_slice(1).to_a
S = Struct.new(:a, :b)
out << S.new(1, 2).to_a
blk = proc { |x, k: 0| [x, k] }
out << blk.call(1, k: 2) << blk.call({k: 3})
out << [[1, {k: 2}]].map { |a, b| b }
p out
