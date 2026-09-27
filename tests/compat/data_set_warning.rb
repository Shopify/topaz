out = []
Point = Data.define(:x, :y) do
  def norm = x * x + y * y
end
a = Point.new(1, 2); b = Point.new(x: 1, y: 2)
out << a.inspect << (a == b) << a.eql?(b) << (a.hash == b.hash) << a.to_h << a.norm << a.frozen? << Point.members << a.with(y: 5).inspect << Point[3, 4].inspect << a.deconstruct_keys([:x]) << a.deconstruct
begin; Point.new(1); rescue => e; out << [e.class, e.message]; end
begin; Point.new(1, 2, 3); rescue => e; out << [e.class, e.message]; end
begin; Point.new(x: 1, y: 2, z: 3); rescue => e; out << [e.class, e.message]; end
Empty = Data.define
out << Empty.new.inspect << Point.new(x: 1, y: "s").inspect << Point.superclass
D2 = Data.define(:a) { def initialize(a: 0) = super }
out << D2.new.inspect
case a; in {x:, y:} then out << [x, y]; end
out << Data.define(:v).new(v: 1).to_s
out << Set[1, 2, 3].inspect << Set.new([1, 1]).size << Set[1].include?(1) << Set[Set[1]].inspect
out << Warning[:deprecated] << Warning[:experimental] << Warning.categories
p out
