# Usage: bin/topaz bench/unpack_utf8.rb unpack|unpack1|bulk ascii|utf8 constant|mutable [repeats] [codepoints]
# Prints five timings in seconds. Discard the first sample as warmup.
def single_unpack(values, count)
  i = 0
  total = 0
  while i < count
    total += values[i & 1].unpack('U')[0]
    i += 1
  end
  total
end

def single_unpack1(values, count)
  i = 0
  total = 0
  while i < count
    total += values[i & 1].unpack1('U')
    i += 1
  end
  total
end

def bulk_unpack(values, count)
  i = 0
  total = 0
  while i < count
    result = values[i & 1].unpack('U*')
    total += result.length + result[0]
    i += 1
  end
  total
end

mode = ARGV[0] || 'unpack'
kind = ARGV[1] || 'utf8'
storage = ARGV[2] || 'constant'
repeats = (ARGV[3] || '1').to_i
target = (ARGV[4] || '1000000').to_i
raise 'invalid mode' unless ['unpack', 'unpack1', 'bulk'].include?(mode)
raise 'invalid character kind' unless ['ascii', 'utf8'].include?(kind)
raise 'invalid storage' unless ['constant', 'mutable'].include?(storage)
raise 'invalid repetition count' unless repeats > 0
raise 'invalid codepoint count' unless target > 0

if kind == 'ascii'
  values = ['a', 'b']
  first_sum = 195
  width = 1
elsif mode == 'bulk'
  values = ["a\xc3\xa9\xe2\x82\xac\xf0\x9d\x84\x9e",
            "b\xc3\xaa\xe2\x82\xad\xf0\x9d\x84\x9f"]
  first_sum = 195
  width = 4
else
  values = ["\xc3\xa9", "\xc3\xaa"]
  first_sum = 467
  width = 1
end
values = values.map { |s| s * repeats } if mode == 'bulk'
values.each { |s| s << '' } if storage == 'mutable'
count = mode == 'bulk' ? [target / (width * repeats), 200].max : target
count -= count & 1
expected = first_sum * (count / 2)
expected += width * repeats * count if mode == 'bulk'

# Large inputs need few outer iterations per sample. Warm that caller too,
# so their samples compare compiled callers rather than threshold crossings.
case mode
when 'unpack'; single_unpack(values, 10000)
when 'unpack1'; single_unpack1(values, 10000)
else; bulk_unpack(values, 2000)
end

5.times do
  start = Time.now
  result = case mode
           when 'unpack'; single_unpack(values, count)
           when 'unpack1'; single_unpack1(values, count)
           else; bulk_unpack(values, count)
           end
  elapsed = Time.now - start
  raise 'incorrect codepoints' unless result == expected
  puts elapsed
end
