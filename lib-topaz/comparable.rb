module Comparable
  def >(other)
    return Topaz.compare(self, other) > 0
  end

  def <(other)
    return Topaz.compare(self, other) < 0
  end

  def >=(other)
    return Topaz.compare(self, other) >= 0
  end

  def <=(other)
    return Topaz.compare(self, other) <= 0
  end

  def ==(other)
    begin
      compared = (self <=> other)
    rescue StandardError
      return false
    end

    return compared == 0
  end

  def between?(min, max)
    return self >= min && self <= max
  end
end

module Comparable
  # Ruby 2.4; the range form is Ruby 2.7
  def clamp(min, max = nil)
    if max.nil? && min.is_a?(Range)
      range = min
      min = range.begin
      max = range.end
      if range.exclude_end? && !max.nil?
        raise ArgumentError.new("cannot clamp with an exclusive range")
      end
    end
    if !min.nil? && !max.nil? && (min <=> max) > 0
      raise ArgumentError.new("min argument must be less than or equal to max argument")
    end
    return min if !min.nil? && (self <=> min) < 0
    return max if !max.nil? && (self <=> max) > 0
    self
  end
end
