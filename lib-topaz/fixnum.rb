class Topaz::Fixnum < Integer
  def next
    succ
  end

  def succ
    self + 1
  end

  def upto(n, &block)
    return self.enum_for(:upto, n) if !block
    i = self
    while i <= n
      yield i
      i += 1
    end
    self
  end

  def even?
    self % 2 == 0
  end

  def odd?
    self % 2 != 0
  end

  def __id__
    self * 2 + 1
  end

  def magnitude
    abs
  end

  # MRI semantics: a Float anywhere makes the sequence Float and counts
  # steps up front (as Range#step does) to avoid accumulating error;
  # otherwise values are added until the limit is passed, downwards for a
  # negative step, and forever when there is no limit.
  def step(limit = (no_limit = true; nil), step = (no_step = true; 1), by: nil, to: nil, &block)
    unless by.nil?
      raise ArgumentError, "step is given twice" unless no_step
      step = by
    end
    unless to.nil?
      raise ArgumentError, "to is given twice" unless no_limit
      limit = to
    end
    step = 1 if step.nil?
    raise ArgumentError, "step can't be 0" if step == 0
    return enum_for(:step, limit, step) { __topaz_step_size(limit, step) } unless block

    if step.is_a?(Float) || limit.is_a?(Float)
      __topaz_float_step(limit, step, &block)
    elsif limit.nil?
      i = self
      while true
        yield i
        i += step
      end
    elsif !step.is_a?(Numeric)
      raise ArgumentError, "comparison of #{step.class} with 0 failed"
    elsif !(limit.is_a?(Integer) && step.is_a?(Integer) && __topaz_int_step(limit, step, &block))
      i = self
      if step > 0
        while i <= limit
          yield i
          i += step
        end
      else
        while i >= limit
          yield i
          i += step
        end
      end
    end
    self
  end

  def __topaz_step_size(limit, step)
    return Float::INFINITY if limit.nil?
    if step.is_a?(Float) || limit.is_a?(Float)
      n = __topaz_float_step_count(to_f, limit.to_f, step.to_f)
      return n < 0 ? 0 : n
    end
    n = ((limit - self) / step).floor + 1
    n < 0 ? 0 : n
  end

  def __topaz_float_step_count(first, last, step)
    return Float::INFINITY if step.infinite?
    n = (last - first) / step
    err = (first.abs + last.abs + (last - first).abs) / step.abs * Float::EPSILON
    return Float::INFINITY if n.infinite?
    err = 0.5 if err > 0.5
    (n + err).floor + 1
  end

  def __topaz_float_step(limit, step)
    first = to_f
    step = step.to_f
    if limit.nil?
      i = 0
      while true
        yield first + i * step
        i += 1
      end
    end
    last = limit.to_f
    n = __topaz_float_step_count(first, last, step)
    if n.infinite?
      i = 0
      while true
        yield first + i * step
        i += 1
      end
    end
    i = 0
    while i < n
      d = i * step + first
      d = last if step > 0 ? last < d : last > d
      yield d
      i += 1
    end
    self
  end
end
