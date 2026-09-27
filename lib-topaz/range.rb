class Range
  def each(&block)
    return self.enum_for unless block
    unless self.begin.respond_to?(:succ)
      raise TypeError.new("can't iterate from #{self.begin.class}")
    end

    if self.end.nil?
      # An endless range (Ruby 2.6).
      i = self.begin
      while true
        yield i
        i = i.succ
      end
    end

    case self.begin
    when String
      self.begin.upto(self.end, self.exclude_end?, &block)
    when Symbol
      self.begin.to_s.upto(self.end.to_s, self.exclude_end?) do |s|
        yield s.to_sym
      end
    else
      i = self.begin
      if self.exclude_end?
        while (i <=> self.end) < 0 do
          yield i
          i = i.succ
        end
      else
        while (i <=> self.end) <= 0 do
          yield i
          i = i.succ
        end
      end
    end
    self
  end

  def step(step_size = 1, &block)
    return self.to_enum(:step, step_size) unless block
    first = self.begin
    last = self.end

    if last.nil? && step_size.kind_of?(Float)
      first = Float(first)
    elsif step_size.kind_of? Float or first.kind_of? Float or last.kind_of? Float
      # if any are floats they all must be
      begin
        step_size = Float(from = step_size)
        first     = Float(from = first)
        last      = Float(from = last)
      rescue ArgumentError
        raise TypeError, "no implicit conversion to float from #{from.class}"
      end
    else
      step_size = Topaz.convert_type(step_size, Integer, :to_int)
    end

    if step_size <= 0
      raise ArgumentError, "step can't be negative" if step_size < 0
      raise ArgumentError, "step can't be 0"
    end

    if first.kind_of?(Float) && !last.nil?
      err = (first.abs + last.abs + (last - first).abs) / step_size.abs * Float::EPSILON
      err = 0.5 if err > 0.5
      if self.exclude_end?
        n = ((last - first) / step_size - err).floor
        n += 1 if n * step_size + first < last
      else
        n = ((last - first) / step_size + err).floor + 1
      end

      i = 0
      while i < n
        d = i * step_size + first
        d = last if last < d
        yield d
        i += 1
      end
    elsif first.kind_of?(Numeric)
      d = first
      while last.nil? || (self.exclude_end? ? d < last : d <= last)
        yield d
        d += step_size
      end
    else
      counter = 0
      each do |o|
        yield o if counter % step_size == 0
        counter += 1
      end
    end

    return self
  end

  def first(*args)
    if self.begin.nil?
      raise RangeError.new("cannot get the first element of beginless range")
    end
    if args.empty?
      self.begin
    else
      take(*args)
    end
  end

  def last(*args)
    if self.end.nil?
      raise RangeError.new("cannot get the last element of endless range")
    end
    args.empty? ? self.end : self.to_a.last(*args)
  end

  def to_a
    if self.end.nil?
      raise RangeError.new("cannot convert endless range to an array")
    end
    super
  end
  alias entries to_a

  def size
    b = self.begin
    unless b.kind_of?(Integer)
      raise TypeError.new("can't iterate from #{b.class}") if b.nil? || b.kind_of?(Float)
      return nil
    end
    e = self.end
    return Float::INFINITY if e.nil?
    return nil unless e.kind_of?(Numeric)
    last = e.floor
    last -= 1 if self.exclude_end? && last == e
    last < b ? 0 : last - b + 1
  end

  def count(*args, &block)
    return Float::INFINITY if args.empty? && !block && self.end.nil?
    super
  end

  def min(&block)
    if self.begin.nil?
      raise RangeError.new("cannot get the minimum of beginless range")
    end
    return super(&block) if block
    return self.begin if self.end.nil?
    if (self.end < self.begin) || (self.exclude_end? && (self.end == self.begin))
      return nil
    end
    self.begin
  end

  def max(&block)
    if self.end.nil?
      raise RangeError.new("cannot get the maximum of endless range")
    end
    return self.end if self.begin.nil? && !self.exclude_end?
    return super(&block) if block || (self.exclude_end? && !self.end.kind_of?(Numeric))
    if (self.end < self.begin) || (self.exclude_end? && (self.end == self.begin))
      return nil
    end
    if self.exclude_end?
      unless self.end.kind_of?(Integer)
        raise TypeError.new("cannot exclude non Integer end value")
      end
      unless self.end.kind_of?(Integer)
        raise TypeError.new("cannot exclude end value with non Integer begin value")
      end
      self.end - 1
    else
      self.end
    end
  end

  def ===(value)
    self.include?(value)
  end

  def include?(value)
    unless self.begin.nil?
      beg_compare = self.begin <=> value
      return false if !beg_compare || beg_compare > 0
    end
    return true if self.end.nil?
    end_compare = value <=> self.end
    return false if !end_compare
    self.exclude_end? ? end_compare < 0 : end_compare <= 0
  end
  alias cover? include?
  alias member? include?

  def ==(other)
    return true if self.equal?(other)
    return false unless other.kind_of?(Range)

    return self.exclude_end? == other.exclude_end? &&
           self.begin == other.begin &&
           self.end == other.end
  end

  alias eql? ==

  def to_s
    "#{self.begin}#{self.exclude_end? ? '...' : '..'}#{self.end}"
  end

  def inspect
    b = (self.begin.nil? && !self.end.nil?) ? "" : self.begin.inspect
    e = (self.end.nil? && !self.begin.nil?) ? "" : self.end.inspect
    "#{b}#{self.exclude_end? ? '...' : '..'}#{e}"
  end
end
