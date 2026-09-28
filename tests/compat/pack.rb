# Array#pack and String#unpack, compared byte by byte.
[
  [[1, 2], "C*"], [[65, 66, 67], "C*"], [[-1, 300], "cS"], [[1], "N"], [[1], "n"], [[1], "V"], [[1], "v"],
  [[-2], "l"], [[-2], "q"], [[2**40], "Q>"], [[1, 2], "s<s>"], [[2**63], "J"], [[1], "L_"],
  [["abc"], "m"], [["abc"], "m0"], [["a" * 50], "m"], [[""], "m"], [["hello world"], "m0"],
  [["ab", "c"], "A3a3"], [["ab"], "Z*"], [["abcd"], "Z2"], [["1011"], "B*"], [["1011"], "b*"],
  [["4a6f"], "H*"], [["4a6"], "H*"], [["a4f6"], "h*"], [[0x263a, 0x41], "U*"], [[300, 5], "w*"],
  [[1.5], "E"], [[1.5], "G"], [[1.5], "e"], [[1.5], "d"], [["hi there"], "u"], [["caf\xC3\xA9 = x\n"], "M"],
  [[1, 2], "Cx2C"], [[1, 2, 3], "CCXC"], [[1, 2], "C@4C"], [[1, 2], "C # comment\nC"],
].each do |items, template|
  puts "#{items.inspect}.pack(#{template.inspect}) = #{items.pack(template).bytes.inspect}"
end

[
  ["\x01\x02", "C*"], ["\xff\xfe", "c*"], ["\x00\x00\x00\x01", "N"], ["\x01\x00", "v"], ["\xfe\xff\xff\xff", "l"],
  ["\xff" * 8, "Q"], ["\xff" * 8, "q>"], ["\x01\x02\x03\x04\x05\x06\x07\x08", "J"],
  ["YWJj\n", "m"], ["YWJj", "m0"], ["aGVsbG8gd29ybGQ=", "m0"], ["aGVsbG8gd29ybGQ", "m"],
  ["ab  \0", "A*"], ["ab\0cd", "Z*a*"], ["ab\0cd", "a*"], ["\xb0", "B*"], ["\xb0", "b*"], ["Jo", "H*"], ["Jo", "h*"],
  ["\xE2\x98\xBAA", "U*"], ["\x82\x2c\x05", "w*"], ["\x00\x00\x00\x00\x00\x00\xf8\x3f", "E"],
  ["?\xf8\x00\x00\x00\x00\x00\x00", "G"], ["\x00\x00\xc0\x3f", "e"], [["hi there"].pack("u"), "u"],
  ["caf=C3=A9 =3D x\n", "M"], ["abc", "N"], ["\x01\x02\x03", "Cx*"], ["\x01\x02\x03", "C@2C"],
].each do |str, template|
  # Strings are shown as bytes: topaz has no binary encoding to inspect them with.
  result = str.unpack(template).map { |x| x.is_a?(String) ? x.bytes : x }
  puts "#{str.bytes.inspect}.unpack(#{template.inspect}) = #{result.inspect}"
end

p "YWJj".unpack1("m0").bytes, "\x01\x02".unpack1("C", offset: 1), "abc".unpack1("a*").bytes, "".unpack1("N")
p [1, 2].pack("C*", buffer: +"x").bytes
[-> { "!!!!".unpack1("m0") }, -> { [1].pack("C>") }, -> { [1].pack("S<>") }, -> { [].pack("N") },
 -> { [1].pack("y") }, -> { "x".unpack("y") }, -> { ["a"].pack("C") }].each do |f|
  f.call
rescue => e
  p [e.class, e.message]
end
