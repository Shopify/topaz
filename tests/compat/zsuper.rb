class P
  def m(a, b = 2, *r, k: 1, **o, &blk) = [a, b, r, k, o, blk&.call]
end
class C < P
  def m(a, b = 5, *r, k: 9, **o, &blk)
    [1].map { super }.first
  end
end
class D < P
  def m(a, k: 3) = super
end
out = []
out << C.new.m(1) << C.new.m(1, 2, 3, k: 4, z: 5) { :blk } << D.new.m(7) << D.new.m(7, k: 8)
p out
