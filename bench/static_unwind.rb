# Matched benchmark: N=1000000 REPEATS=5 topaz bench/static_unwind.rb
# First two samples warm the JIT; report the remaining samples separately.
N = Integer(ENV.fetch('N', '1000000'))
REPEATS = Integer(ENV.fetch('REPEATS', '5'))

def plain(n)
  i = 0
  while i < n
    i += 1
  end
  i
end

def rescue_normal(n)
  i = 0
  while i < n
    begin
      i += 1
    rescue
      raise 'unexpected exception'
    end
  end
  i
end

def ensure_normal(n)
  i = 0; clean = 0
  while i < n
    begin
      i += 1
    ensure
      clean += 1
    end
  end
  clean
end

def ensure_next(n)
  i = 0; clean = 0
  while i < n
    begin
      i += 1
      next
    ensure
      clean += 1
    end
  end
  clean
end

def raised(n)
  i = 0
  while i < n
    begin
      raise 'expected'
    rescue => e
      # Keep the exception observable so the JIT cannot remove its allocation.
      $last_unwind_error = e
      i += 1
    end
  end
  i
end

def exit_block
  1.times do
    begin
      return 1
    ensure
      nil
    end
  end
end

def nonlocal(n)
  i = 0
  while i < n
    i += exit_block
  end
  i
end

def inner
  i = 0
  while i < 50
    i += 1
  end
  i
end

def escaped(n)
  total = 0
  n.times do
    begin
      total += inner
    ensure
      nil
    end
  end
  total / 50
end

[:plain, :rescue_normal, :ensure_normal, :ensure_next, :raised, :nonlocal, :escaped].each do |name|
  count = name == :raised ? N / 100 : (name == :ensure_next ? N / 50 : N)
  REPEATS.times do |sample|
    start = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    result = send(name, count)
    elapsed = Process.clock_gettime(Process::CLOCK_MONOTONIC) - start
    raise 'wrong result' unless result == count
    puts "#{name},#{sample},#{count},#{elapsed}"
  end
end
