r = []
r << 5.then { |x| x + 1 } << 5.yield_self { _1 * 2 } << 3.itself
r << [1, 2, 3].sum << [0.1, 0.2, 0.3].sum << [1, 2].sum(10) << [1, 2].sum { |x| x * 2 } << (1..100).sum << ["a", "b"].sum("")
r << [1, 2, 3, 4].filter(&:even?) << [1, 2, 3].filter_map { |x| x * 2 if x.odd? } << %w[a b a c a].tally
r << [1, 2].union([2, 3], [4]) << [1, 2, 3, 4].difference([2], [4]) << [1, 2, 3].intersection([2, 3, 4], [3]) << [1, 2].intersect?([2]) << [1, 2].intersect?([3])
r << [1, [2, [3]]].dig(1, 1, 0) << [10, 20, 30].fetch_values(0, 2) << [1, 2, 3, 4].rfind(&:odd?)
r << [1, 3, 5, 7, 9].bsearch { |x| x >= 4 } << [1, 3, 5, 7].bsearch { |x| 5 <=> x }
r << [[1, 2], [3, 4]].to_h << [1, 2].to_h { |x| [x, x * x] } << [1, 2, 4, 9, 10, 11, 12, 15].slice_when { |a, b| b != a + 1 }.to_a << [1, 2, 4, 5, 7].chunk_while { |a, b| b == a + 1 }.to_a
r << [1, nil, 2].compact << [3, 1].append(4) << [3].prepend(0)
h = {a: 1, b: 2, c: nil}
r << h.transform_values { _1.to_s } << h.transform_keys(&:to_s) << h.transform_keys({a: :x}) << h.slice(:a, :c, :z) << h.compact << {a: {b: [5]}}.dig(:a, :b, 0) << h.fetch_values(:a, :b) << h.filter { |k, v| v } << h.to_h { |k, v| [v, k] } << h.sum([]) { |k, v| [k] } << h.filter_map { |k, v| k if v }
r << "hello".match?(/ll/) << "hello".match?("z") << "prefix-x".delete_prefix("prefix-") << "x.rb".delete_suffix(".rb") << "ABC".casecmp?("abc")
r << "aaabbbccc".squeeze << "aaabbb".squeeze("a") << "a\nb\n".lines << "abc".sum << "0x1A".hex << "-ff".hex << "0b101".oct << "777".oct << (+"x").frozen? << (-"y").frozen?
r << 1234.digits << 255.digits(16) << 3.pow(4, 5) << 2.pow(100, 1000) << 0b1010.allbits?(0b1000) << 6.anybits?(1) << 6.nobits?(1) << 7.ceildiv(2) << -7.ceildiv(2) << 12.gcd(18) << 4.lcm(6) << Integer.sqrt(24) << Integer.sqrt(10**20) << Integer.try_convert("x")
r << 15.clamp(1, 10) << 5.clamp(..3) << 1.5.clamp(2, 3) << "b".clamp("a", "c")
r << :foo.start_with?("f") << :foo.end_with?("x") << :foo.name
add = ->(a, b) { a + b }
double = proc { |x| x * 2 }
r << (double >> ->(x) { x + 1 }).call(3) << (double << ->(x) { x + 1 }).call(3) << add.curry[1][2] << 5.method(:+).curry[3] << (5.method(:+) >> double).call(1)
r << (1..5).overlap?(5..7) << (1...5).overlap?(5..7) << (1..).overlap?(0..1) << ((1..10) % 3).to_a
r << Math.log1p(0.5).round(10) << Math.expm1(1.0).round(10) << Math.log1p(-1.0)
p r
