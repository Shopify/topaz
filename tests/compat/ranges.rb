a = [1, 2, 3, 4, 5]
out = []
out << a[2..] << a[..1] << a[1...] << "hello"[1..] << "hello"[..-2]
out << (1..).first(3) << (1..).take(2) << (1..).each_slice(2).first(2)
out << (1..).include?(1000) << (..5).include?(3) << (..5).include?(6) << (1...).cover?(0)
out << (1..).inspect << (..5).inspect << (nil..nil).inspect << (1..).to_s << ("a".."b").inspect
out << (1..).size << (1..10).size << (1...10).size << (1..3.5).size
out << ((1..) == (1..)) << ((1..2) == (1..3))
begin; (1..).to_a; rescue RangeError => e; out << e.message; end
begin; (..1).each {}; rescue TypeError => e; out << e.message; end
r = []
(1..).each { |i| r << i; break if i >= 3 }
out << r << (1..).step(3).first(3) << (1.0..).step(0.5).first(3)
x = case 5 when (..3) then :low when (4..) then :high end
out << x << (5..).min << (..5).max
p out
