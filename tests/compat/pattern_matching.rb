out = []
def m(v)
  case v
  in Integer | Float => n if n > 100 then [:big, n]
  in Integer => n then [:int, n]
  in [] then :empty
  in [1, *rest] then [:one, rest]
  in [Integer => a, String => b] then [:pair, a, b]
  in [*, :needle, *post] then [:found, post]
  in {name: String => name, age: Integer => age} then [:person, name, age]
  in {type: :point, **rest} then [:point, rest]
  in {} then :empty_hash
  in nil then :nil
  in String if v.empty? then :empty_string
  in /\A\d+\z/ then :digits
  in ^$pinned then :pinned
  else [:other, v]
  end
end
$pinned = "pin"
[150, 7, 2.5, [], [1, 2, 3], [5, "x"], [0, :needle, 9, 8], {name: "Al", age: 3}, {type: :point, x: 1}, {}, nil, "", "123", "pin", :sym].each { |v| out << m(v) }
x = [1, [2, 3]]
x => [a, [b, c]]
out << [a, b, c]
out << (5 in Integer) << ("s" in Integer)
begin
  1 => String
rescue NoMatchingPatternError => e
  out << [e.class, e.message]
end
begin
  case 5; in String then 1; end
rescue NoMatchingPatternError => e
  out << e.message
end
Point = Struct.new(:x, :y)
case Point.new(1, 2)
in [x, y] then out << [:struct_array, x, y]
end
case Point.new(1, 2)
in {x:, y:} then out << [:struct_hash, x, y]
end
out << (case {a: 1, b: 2}; in {a: 1, **nil} then :exact; in {a: 1} then :subset; end)
out << (case 5; in ..3 then :low; in 4.. then :high; end)
p out
