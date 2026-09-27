out = []
def target(*args, **kw, &blk)
  [args, kw, blk ? blk.call : nil]
end
def fwd(...) = target(...)
def fwd2(a, ...) = target(a, 0, ...)
def rest(*) = target(*)
def kws(**) = target(**)
def blk(&) = target(&)
out << fwd(1, 2, k: 3) { :b }
out << fwd2(1, 2)
out << rest(1, 2)
out << kws(a: 1)
out << blk { :x }
class P; def m(*a, &b) = [a, b&.call]; end
class C < P; def m(...) = super(...); end
out << C.new.m(1) { 2 }
p out
