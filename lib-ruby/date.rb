# Date and DateTime. The classes are in lib-ruby/ext/date_core.rb, which
# stands in for CRuby's date_core extension; this is the date gem's Ruby
# part.
require "date_core"

class Date
  VERSION = "3.4.1"

  def infinite?
    false
  end

  class Infinity < Numeric
    def initialize(d = 1)
      @d = d <=> 0
    end

    def d
      @d
    end
    protected :d

    def zero?
      false
    end

    def finite?
      false
    end

    def infinite?
      d.nonzero?
    end

    def nan?
      d.zero?
    end

    def abs
      self.class.new
    end

    def -@
      self.class.new(-d)
    end

    def +@
      self.class.new(+d)
    end

    def <=>(other)
      case other
      when Infinity
        d <=> other.d
      when Float::INFINITY
        d <=> 1
      when -Float::INFINITY
        d <=> -1
      when Numeric
        d
      end
    end

    def coerce(other)
      case other
      when Numeric
        [-d, d]
      else
        super
      end
    end

    def to_f
      return 0 if @d == 0
      @d > 0 ? Float::INFINITY : -Float::INFINITY
    end
  end
end
