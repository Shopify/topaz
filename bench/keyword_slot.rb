# Materialized calls across a compiled-loop boundary, with and without
# optional keyword bookkeeping. Run each mode with both comparison binaries:
# MODE=plain|omitted|supplied N=10000000 topaz bench/keyword_slot.rb
# Output: mode, sample, phase, calls, inner iterations, elapsed seconds.
MODE = ENV.fetch('MODE', 'plain')
N = Integer(ENV.fetch('N', '10000000'))
INNER = Integer(ENV.fetch('INNER', '5'))
WARMUP = Integer(ENV.fetch('WARMUP', '2'))
SAMPLES = Integer(ENV.fetch('SAMPLES', '5'))

if MODE == 'plain'
  def inner(n)
    i = 0
    while i < n
      i += 1
    end
    i
  end
elsif MODE == 'omitted' || MODE == 'supplied'
  def inner(n, k: 0)
    i = 0
    while i < n
      i += 1
    end
    i + k
  end
else
  raise 'unknown mode'
end

if MODE == 'supplied'
  def calls(n, iterations)
    i = 0
    total = 0
    while i < n
      total += inner(iterations, k: 1)
      i += 1
    end
    total
  end
else
  def calls(n, iterations)
    i = 0
    total = 0
    while i < n
      total += inner(iterations)
      i += 1
    end
    total
  end
end

# Compile the callee before the caller, including for short inner loops.
raise 'wrong warmup result' unless inner(100000) == 100000
expected = N * (INNER + (MODE == 'supplied' ? 1 : 0))
sample = 0
while sample < WARMUP + SAMPLES
  start = Process.clock_gettime(Process::CLOCK_MONOTONIC)
  result = calls(N, INNER)
  elapsed = Process.clock_gettime(Process::CLOCK_MONOTONIC) - start
  raise 'wrong result' unless result == expected
  phase = sample < WARMUP ? 'warmup' : 'measure'
  puts "#{MODE},#{sample},#{phase},#{N},#{INNER},#{elapsed}"
  sample += 1
end
