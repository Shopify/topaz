out = []
out << [1, 2].map { it * 2 } << [[1, 2]].map { _1 + _2 }
def sq(x) = x * x
out << sq(4)
x = 1
def y = 2
out << {x:, y:}
out << (nil&.foo) << ("ab"&.length)
if /(?<year>\d+)-(?<mon>\d+)/ =~ "2025-12"
  out << [year, mon]
end
r = [1, 0].map do |d|
  10 / d
rescue ZeroDivisionError
  :inf
end
out << r
out << <<~EOS
  one
    two
EOS
v = nil
  || 42
out << v
out << %i[a b] << %w[c d]
out << (case [1, [2, 3]]
        in [a, [b, *]] then [a, b]
        end)
p out
