# break from a block, many times over so that the JIT compiles the method:
# the translated JIT once marked the method's interpreter finished after
# the first break left an inlined call, and the next break raised
# "break from proc-closure".
def first_break
  i = 0
  while i < 2
    i += 1
    x = [1].each { break i * 10 }
  end
  x
end

def loop_break(s)
  out = +""
  i = 0
  while i < s.size
    loop do
      out << s[i]
      i += 1
      break
    end
  end
  out
end

total = 0
3000.times { total += first_break }
p total
p 3000.times.map { loop_break("abc") }.uniq
p 3000.times.map { |i| "%%%02X" % (i % 256) }.last
