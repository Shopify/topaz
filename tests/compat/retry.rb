tries = 0
r = begin
  tries += 1
  raise "boom" if tries < 3
  :done
rescue => e
  retry if tries < 3
  :failed
end
out = [r, tries]
def m
  n = 0
  begin
    n += 1
    raise ArgumentError if n < 2
    n
  rescue ArgumentError
    retry
  end
end
out << m
[1].each do |x|
  k = 0
  begin
    k += 1
    raise "x" if k < 4
  rescue
    retry
  end
  out << k
end
p out
