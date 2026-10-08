# Rational numbers: a numerator and a positive denominator, in lowest
# terms.
class Rational < Numeric
  def self.__topaz_new(num, den)
    if den == 0
      raise ZeroDivisionError, "divided by 0"
    end
    if den < 0
      num = -num
      den = -den
    end
    g = num.gcd(den)
    if g != 1
      num /= g
      den /= g
    end
    r = allocate
    r.__send__(:__topaz_init, num, den)
    r
  end

  class << self
    undef_method :new rescue nil
  end

  def numerator
    @num
  end

  def denominator
    @den
  end

  def +(other)
    case other
    when Rational
      Rational.__topaz_new(@num * other.denominator + other.numerator * @den, @den * other.denominator)
    when Integer
      Rational.__topaz_new(@num + other * @den, @den)
    when Float
      to_f + other
    else
      a, b = other.coerce(self)
      a + b
    end
  end

  def -(other)
    case other
    when Rational
      Rational.__topaz_new(@num * other.denominator - other.numerator * @den, @den * other.denominator)
    when Integer
      Rational.__topaz_new(@num - other * @den, @den)
    when Float
      to_f - other
    else
      a, b = other.coerce(self)
      a - b
    end
  end

  def *(other)
    case other
    when Rational
      Rational.__topaz_new(@num * other.numerator, @den * other.denominator)
    when Integer
      Rational.__topaz_new(@num * other, @den)
    when Float
      to_f * other
    else
      a, b = other.coerce(self)
      a * b
    end
  end

  def /(other)
    case other
    when Rational
      raise ZeroDivisionError, "divided by 0" if other.numerator == 0
      Rational.__topaz_new(@num * other.denominator, @den * other.numerator)
    when Integer
      raise ZeroDivisionError, "divided by 0" if other == 0
      Rational.__topaz_new(@num, @den * other)
    when Float
      to_f / other
    else
      a, b = other.coerce(self)
      a / b
    end
  end
  alias quo /

  def fdiv(other)
    to_f / other
  end

  def **(other)
    if other.is_a?(Integer)
      if other >= 0
        Rational.__topaz_new(@num**other, @den**other)
      else
        raise ZeroDivisionError, "divided by 0" if @num == 0
        Rational.__topaz_new(@den**-other, @num**-other)
      end
    elsif other.is_a?(Rational) && other.denominator == 1
      self**other.numerator
    else
      to_f**other.to_f
    end
  end

  def -@
    Rational.__topaz_new(-@num, @den)
  end

  def +@
    self
  end

  def abs
    @num < 0 ? -self : self
  end
  alias magnitude abs

  def <=>(other)
    case other
    when Rational
      (@num * other.denominator) <=> (other.numerator * @den)
    when Integer
      @num <=> other * @den
    when Float
      to_f <=> other
    else
      if other.respond_to?(:coerce)
        a, b = other.coerce(self)
        a <=> b
      end
    end
  end

  def ==(other)
    case other
    when Rational
      @num == other.numerator && @den == other.denominator
    when Integer
      @den == 1 && @num == other
    when Float
      to_f == other
    else
      other == self
    end
  end

  def eql?(other)
    other.is_a?(Rational) && self == other
  end

  def hash
    [@num, @den].hash
  end

  def coerce(other)
    case other
    when Integer
      [Rational.__topaz_new(other, 1), self]
    when Float
      [other, to_f]
    when Rational
      [other, self]
    else
      raise TypeError, "#{other.class} can't be coerced into Rational"
    end
  end

  def zero?
    @num == 0
  end

  def positive?
    @num > 0
  end

  def negative?
    @num < 0
  end

  def finite?
    true
  end

  def infinite?
    nil
  end

  def integer?
    false
  end

  def floor(digits = nil)
    return @num.div(@den) if digits.nil? || digits == 0
    __topaz_round_to(digits) { |x| x.floor }
  end

  def ceil(digits = nil)
    return -((-@num).div(@den)) if digits.nil? || digits == 0
    __topaz_round_to(digits) { |x| x.ceil }
  end

  def truncate(digits = nil)
    return (@num < 0 ? -((-@num).div(@den)) : @num.div(@den)) if digits.nil? || digits == 0
    __topaz_round_to(digits) { |x| x.truncate }
  end

  def round(digits = nil, half: :up)
    if digits.nil? || digits == 0
      neg = @num < 0
      q, r = (neg ? -@num : @num).divmod(@den)
      twice = 2 * r
      if twice > @den
        q += 1
      elsif twice == @den
        case half
        when :up, nil then q += 1
        when :even then q += 1 if q.odd?
        when :down then nil
        else raise ArgumentError, "invalid rounding mode: #{half}"
        end
      end
      return neg ? -q : q
    end
    __topaz_round_to(digits) { |x| x.round(half: half) }
  end

  def __topaz_round_to(digits)
    scale = 10**digits.abs
    if digits > 0
      Rational.__topaz_new(yield(self * scale), scale)
    else
      yield(self / scale) * scale
    end
  end

  def to_i
    truncate
  end

  def to_f
    return @num.to_f / @den.to_f if @num.abs < 2**53 && @den < 2**53
    # Keep precision for large parts.
    shift = [@num.abs.bit_length, @den.bit_length].max - 60
    shift = 0 if shift < 0
    (@num >> shift).to_f / (@den >> shift).to_f
  end

  def to_r
    self
  end

  def rationalize(eps = nil)
    return self if eps.nil?
    eps = eps.abs.to_r
    a = self - eps
    b = self + eps
    return self if a == b
    Rational.__topaz_simplest(a, b)
  end

  # The simplest rational in [a, b].
  def self.__topaz_simplest(a, b)
    if a.floor == a
      return Rational.__topaz_new(a.floor, 1)
    end
    if a.floor < b.floor
      return Rational.__topaz_new(a.floor + 1, 1)
    end
    fl = a.floor
    rest = __topaz_simplest(1 / (b - fl), 1 / (a - fl))
    fl + 1 / rest
  end

  def to_s
    "#{@num}/#{@den}"
  end

  def inspect
    "(#{@num}/#{@den})"
  end

  def divmod(other)
    q = (self / other).floor
    [q, self - other * q]
  end

  def div(other)
    (self / other).floor
  end

  def %(other)
    self - other * (self / other).floor
  end
  alias modulo %

  def remainder(other)
    self - other * (self / other).truncate
  end

  def marshal_dump
    [@num, @den]
  end

  def marshal_load(array)
    __topaz_init(array[0], array[1])
  end

  private

  def __topaz_init(num, den)
    @num = num
    @den = den
  end
end

module Kernel
  def Rational(a, b = 1, exception: true)
    # Integer pairs are the common case (Time#subsec, Time#to_r); build the
    # result directly instead of converting both to Rationals and dividing.
    return Rational.__topaz_new(a, b) if a.is_a?(Integer) && b.is_a?(Integer)
    a = Topaz.__topaz_to_rational(a, exception)
    return nil if a.nil?
    return a if b == 1
    b = Topaz.__topaz_to_rational(b, exception)
    return nil if b.nil?
    a / b
  end
  private :Rational
end

module Topaz
  def self.__topaz_to_rational(x, exception = true)
    case x
    when Rational then x
    when Integer then Rational.__topaz_new(x, 1)
    when Float then x.to_r
    when String
      s = x.strip
      m = s.match(/\A([-+]?)(\d[\d_]*)?(?:\.(\d[\d_]*))?(?:[eE]([-+]?\d+))?(?:\/(\d[\d_]*))?\z/)
      if m.nil? || (m[2].nil? && m[3].nil?)
        raise ArgumentError, "invalid value for convert(): #{x.inspect}" if exception
        return nil
      end
      int = (m[2] || "0").delete("_")
      frac = (m[3] || "").delete("_")
      num = (int + frac).to_i
      den = 10**frac.size
      if m[4]
        e = m[4].to_i
        e >= 0 ? num *= 10**e : den *= 10**-e
      end
      den *= m[5].delete("_").to_i if m[5]
      r = Rational.__topaz_new(num, den)
      m[1] == "-" ? -r : r
    when nil
      raise TypeError, "can't convert nil into Rational" if exception
      nil
    else
      if x.respond_to?(:to_r)
        x.to_r
      else
        raise TypeError, "can't convert #{x.class} into Rational" if exception
        nil
      end
    end
  end
end

class Integer
  def to_r
    Rational.__topaz_new(self, 1)
  end

  def rationalize(eps = nil)
    to_r
  end

  def numerator
    self
  end

  def denominator
    1
  end
end

class Float
  # The exact value of this float.
  def to_r
    raise FloatDomainError, to_s if nan? || infinite?
    return Rational.__topaz_new(0, 1) if self == 0.0
    m, e = Math.frexp(self)
    # m * 2**53 is an integer for a double.
    num = (m * 9007199254740992).to_i
    e -= 53
    e >= 0 ? Rational.__topaz_new(num * 2**e, 1) : Rational.__topaz_new(num, 2**-e)
  end

  def rationalize(eps = nil)
    return to_r.rationalize(eps) if eps
    return Rational.__topaz_new(to_i, 1) if self == to_i
    # The simplest rational that rounds to this float.
    m, e = Math.frexp(self)
    num = (m * 9007199254740992).to_i
    e -= 53
    a = Rational(2 * num - 1, 2) * Rational(2)**e
    b = Rational(2 * num + 1, 2) * Rational(2)**e
    a, b = b, a if a > b
    Rational.__topaz_simplest(a, b)
  end

  def numerator
    to_r.numerator
  end

  def denominator
    to_r.denominator
  end
end

class NilClass
  def to_r
    Rational.__topaz_new(0, 1)
  end

  def rationalize(eps = nil)
    to_r
  end
end

class String
  def to_r
    s = strip
    m = s.match(/\A[-+]?(\d[\d_]*)?(?:\.\d[\d_]*)?(?:[eE][-+]?\d+)?(?:\/\d[\d_]*)?/)
    str = m ? m[0] : ""
    str = "0" if str.empty? || str =~ /\A[-+]?\z/
    Topaz.__topaz_to_rational(str, false) || Rational.__topaz_new(0, 1)
  end
end
