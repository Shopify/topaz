# Three required positional arguments: eligible for send_valuestack.
def leaf(a, b, c)
  a + b + c
end

def run_calls(n)
  i = 0
  result = 0
  while i < n
    result = leaf(i, 3, 4)
    i += 1
  end
  result
end

n = (ARGV[0] || "1000000").to_i
warmup = (ARGV[1] || "100000").to_i
samples = (ARGV[2] || "5").to_i
run_calls(warmup) if warmup > 0
samples.times do
  start = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  result = run_calls(n)
  elapsed = Process.clock_gettime(Process::CLOCK_MONOTONIC) - start
  raise 'wrong result' unless result == n + 6
  puts elapsed
end
