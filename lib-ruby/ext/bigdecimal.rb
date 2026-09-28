# The C half of bigdecimal (bigdecimal.so) in Ruby. The gem's own
# bigdecimal.rb (power, sqrt, log, exp) and bigdecimal/util.rb run on top.
#
# A finite value is sign * coefficient * 10**exponent, with the
# coefficient an Integer kept free of trailing zeros; NaN and the
# infinities are flagged. Every result is exact unless a precision is
# asked for or implied (division).
class BigDecimal < Numeric
  VERSION = "3.3.1"
  BASE = 1_000_000_000

  EXCEPTION_ALL = 0xff
  EXCEPTION_NaN = 0x02
  EXCEPTION_INFINITY = 0x01
  EXCEPTION_UNDERFLOW = 0x04
  EXCEPTION_OVERFLOW = 0x01
  EXCEPTION_ZERODIVIDE = 0x10
  ROUND_MODE = 0x100
  ROUND_UP = 1
  ROUND_DOWN = 2
  ROUND_HALF_UP = 3
  ROUND_HALF_DOWN = 4
  ROUND_CEILING = 5
  ROUND_FLOOR = 6
  ROUND_HALF_EVEN = 7

  SIGN_NaN = 0
  SIGN_POSITIVE_ZERO = 1
  SIGN_NEGATIVE_ZERO = -1
  SIGN_POSITIVE_FINITE = 2
  SIGN_NEGATIVE_FINITE = -2
  SIGN_POSITIVE_INFINITE = 3
  SIGN_NEGATIVE_INFINITE = -3

  DOUBLE_FIG = 16

  ROUNDING_MODES = {
    up: ROUND_UP, down: ROUND_DOWN, truncate: ROUND_DOWN, half_up: ROUND_HALF_UP,
    default: ROUND_HALF_UP, half_down: ROUND_HALF_DOWN, half_even: ROUND_HALF_EVEN,
    banker: ROUND_HALF_EVEN, ceiling: ROUND_CEILING, ceil: ROUND_CEILING, floor: ROUND_FLOOR,
  }.freeze

  @__exception_mode = 0
  @__rounding_mode = ROUND_HALF_UP
  @__limit = 0

  class << self
    undef_method :new if method_defined?(:new)

    def double_fig
      DOUBLE_FIG
    end

    def mode(which, value = :__none)
      if which == ROUND_MODE
        return @__rounding_mode if value == :__none || value.nil?
        @__rounding_mode = __rounding_mode(value)
      else
        return @__exception_mode & which if value == :__none || value.nil?
        raise ArgumentError, "second argument must be true or false" unless value == true || value == false
        @__exception_mode = value ? (@__exception_mode | which) : (@__exception_mode & ~which)
        @__exception_mode & which
      end
    end

    def limit(digits = nil)
      old = @__limit
      unless digits.nil?
        digits = Integer(digits)
        raise ArgumentError, "argument must be positive" if digits < 0
        @__limit = digits
      end
      old
    end

    def save_limit
      old = @__limit
      yield
    ensure
      @__limit = old
    end

    def save_exception_mode
      old = @__exception_mode
      yield
    ensure
      @__exception_mode = old
    end

    def save_rounding_mode
      old = @__rounding_mode
      yield
    ensure
      @__rounding_mode = old
    end

    def interpret_loosely(string)
      match = string.to_s.match(/\A\s*([+-]?(?:\d[\d_]*)?(?:\.\d[\d_]*)?(?:[eEdD][+-]?\d+)?)/)
      text = match && match[1]
      return __zero(1) if text.nil? || text !~ /\d/
      BigDecimal(text)
    end

    def _load(string)
      BigDecimal(string.to_s.sub(/\A\d+:/, ""))
    end

    def __rounding_mode(mode)
      return ROUNDING_MODES.fetch(mode) { raise ArgumentError, "invalid rounding mode (#{mode})" } if mode.is_a?(Symbol)
      return ROUNDING_MODES.fetch(mode.to_sym) { raise ArgumentError, "invalid rounding mode (#{mode})" } if mode.is_a?(String)
      mode = Integer(mode)
      raise ArgumentError, "invalid rounding mode (#{mode})" unless (ROUND_UP..ROUND_HALF_EVEN).cover?(mode)
      mode
    end

    def __rounding_mode_now
      @__rounding_mode
    end

    def __limit_now
      @__limit
    end

    def __exception_mode_now
      @__exception_mode
    end

    # Internal constructors.
    def __make(sign, coefficient, exponent)
      __build(sign, coefficient, exponent, nil)
    end

    def __zero(sign)
      __build(sign, 0, 0, nil)
    end

    def __nan
      __build(1, 0, 0, :nan)
    end

    def __infinity(sign)
      __build(sign, 0, 0, :infinity)
    end

    def __build(sign, coefficient, exponent, special)
      value = allocate
      value.__send__(:__setup, sign, coefficient, exponent, special)
      value
    end

    # BigDecimal(value, digits) for a String.
    def __parse(string, exception)
      text = string.strip
      case text
      when "Infinity", "+Infinity" then return __infinity(1)
      when "-Infinity" then return __infinity(-1)
      when "NaN" then return __nan
      end
      match = /\A([+-])?(\d(?:_?\d)*)?(?:\.(\d(?:_?\d)*)?)?(?:[eEdD]([+-]?\d+))?\z/.match(text)
      if match.nil? || (match[2].nil? && match[3].nil?)
        return nil unless exception
        raise ArgumentError, "invalid value for BigDecimal(): #{string.inspect}"
      end
      integer = (match[2] || "").delete("_")
      fraction = (match[3] || "").delete("_")
      sign = match[1] == "-" ? -1 : 1
      exponent = (match[4] || "0").to_i - fraction.size
      __make(sign, (integer + fraction).to_i, exponent)
    end
  end

  def self.__convert(value, digits, exception = true)
    case value
    when BigDecimal
      digits && digits > 0 ? value.__round_significant(digits) : value
    when Integer
      result = value < 0 ? __make(-1, -value, 0) : __make(1, value, 0)
      digits && digits > 0 ? result.__round_significant(digits) : result
    when Float
      return __nan if value.nan?
      return __infinity(value > 0 ? 1 : -1) if value.infinite?
      raise ArgumentError, "precision too large." if digits && digits > DOUBLE_FIG + 1
      return __zero((1.0 / value) < 0 ? -1 : 1) if value == 0.0
      result = __parse(value.to_s, true)
      digits && digits > 0 ? result.__round_significant(digits) : result
    when Rational
      raise ArgumentError, "can't omit precision for a Rational." if digits.nil?
      numerator = __convert(value.numerator, nil)
      numerator.div(__convert(value.denominator, nil), digits)
    when String
      result = __parse(value, exception)
      return nil if result.nil?
      digits && digits > 0 ? result.__round_significant(digits) : result
    when nil
      raise TypeError, "can't convert nil into BigDecimal"
    else
      if value.respond_to?(:to_str)
        __convert(value.to_str, digits, exception)
      else
        raise TypeError, "can't convert #{value.class} into BigDecimal"
      end
    end
  end

  # For arithmetic with another number.
  def self.__coerce(value, precision = nil)
    case value
    when BigDecimal then value
    when Integer, Float then __convert(value, 0)
    when Rational then __convert(value, precision || 2 * DOUBLE_FIG)
    else
      raise TypeError, "#{value.class} can't be coerced into BigDecimal"
    end
  end

  def self.__digit_count(n)
    n == 0 ? 0 : n.to_s.size
  end

  protected

  attr_reader :__sign, :__coefficient, :__exponent, :__special

  private

  def __setup(sign, coefficient, exponent, special)
    if special.nil? && coefficient != 0
      while coefficient % 10 == 0
        coefficient /= 10
        exponent += 1
      end
    elsif special.nil?
      exponent = 0
    end
    @__sign = sign < 0 ? -1 : 1
    @__coefficient = coefficient
    @__exponent = exponent
    @__special = special
    freeze
  end

  public

  # Queries

  def nan?
    @__special == :nan
  end

  def infinite?
    @__special == :infinity ? @__sign : nil
  end

  def finite?
    @__special.nil?
  end

  def zero?
    @__special.nil? && @__coefficient == 0
  end

  def nonzero?
    zero? ? nil : self
  end

  def sign
    return SIGN_NaN if nan?
    return @__sign * SIGN_POSITIVE_INFINITE if @__special == :infinity
    return @__sign * SIGN_POSITIVE_ZERO if @__coefficient == 0
    @__sign * SIGN_POSITIVE_FINITE
  end

  def positive?
    !nan? && @__sign > 0 && !zero?
  end

  def negative?
    !nan? && @__sign < 0 && !zero?
  end

  def exponent
    return 0 unless finite? && @__coefficient != 0
    BigDecimal.__digit_count(@__coefficient) + @__exponent
  end

  def n_significant_digits
    return 0 unless finite?
    BigDecimal.__digit_count(@__coefficient)
  end

  def precision
    return 0 unless finite? && @__coefficient != 0
    digits = BigDecimal.__digit_count(@__coefficient)
    @__exponent >= 0 ? digits + @__exponent : [digits, -@__exponent].max
  end

  def scale
    return 0 unless finite? && @__coefficient != 0
    @__exponent < 0 ? -@__exponent : 0
  end

  def precision_scale
    [precision, scale]
  end

  def precs
    digits = n_significant_digits
    [((digits + 8) / 9) * 9, ((digits + 8) / 9 + 2) * 9]
  end

  def split
    digits = case @__special
             when :nan then "NaN"
             when :infinity then "Infinity"
             else @__coefficient == 0 ? "0" : @__coefficient.to_s
             end
    [nan? ? 0 : @__sign, digits, 10, exponent]
  end

  def hash
    [@__sign, @__coefficient, @__exponent, @__special].hash
  end

  # Conversions

  def to_s(format = nil)
    return "NaN" if nan?
    return (@__sign < 0 ? "-Infinity" : "Infinity") if @__special == :infinity
    format = format.to_s if format
    plus = ""
    if format && (format.start_with?("+") || format.start_with?(" "))
      plus = format[0]
      format = format[1..]
    end
    group = format && format[/\d+/] ? format[/\d+/].to_i : 0
    fixed = format && (format.include?("F") || format.include?("f"))
    sign = @__sign < 0 ? "-" : plus
    if @__coefficient == 0
      return sign + "0.0"
    end
    digits = @__coefficient.to_s
    if fixed
      point = digits.size + @__exponent
      if point <= 0
        integer = "0"
        fraction = "0" * -point + digits
      elsif point >= digits.size
        integer = digits + "0" * (point - digits.size)
        fraction = "0"
      else
        integer = digits[0, point]
        fraction = digits[point..]
      end
      if group > 0
        integer = integer.reverse.scan(/.{1,#{group}}/).join(" ").reverse
        fraction = fraction.scan(/.{1,#{group}}/).join(" ")
      end
      "#{sign}#{integer}.#{fraction}"
    else
      digits = digits.scan(/.{1,#{group}}/).join(" ") if group > 0
      "#{sign}0.#{digits}e#{exponent}"
    end
  end

  def inspect
    to_s
  end

  def to_digits
    return to_s if nan? || infinite?
    to_s("F")
  end

  def to_f
    return Float::NAN if nan?
    return @__sign * Float::INFINITY if @__special == :infinity
    return @__sign < 0 ? -0.0 : 0.0 if @__coefficient == 0
    Float(to_s)
  end

  def to_i
    __check_finite_for_integer
    value = if @__exponent >= 0
              @__coefficient * 10**@__exponent
            else
              @__coefficient / 10**-@__exponent
            end
    @__sign * value
  end
  alias to_int to_i

  def to_r
    __check_finite_for_integer("Rational")
    if @__exponent >= 0
      Rational(@__sign * @__coefficient * 10**@__exponent, 1)
    else
      Rational(@__sign * @__coefficient, 10**-@__exponent)
    end
  end

  def to_d
    self
  end

  def _dump(limit = nil)
    "#{n_significant_digits * 1}:#{to_s}"
  end

  def coerce(other)
    [BigDecimal.__coerce(other, n_significant_digits + DOUBLE_FIG), self]
  end

  def clone
    self
  end

  def dup
    self
  end

  def +@
    self
  end

  def -@
    return self if nan?
    BigDecimal.__build(-@__sign, @__coefficient, @__exponent, @__special)
  end

  def abs
    return self if nan?
    BigDecimal.__build(1, @__coefficient, @__exponent, @__special)
  end

  # Arithmetic

  def add(other, digits)
    __limit_result(__add(__operand(other), 1), digits)
  end

  def sub(other, digits)
    __limit_result(__add(__operand(other), -1), digits)
  end

  def mult(other, digits)
    __limit_result(__mult(__operand(other)), digits)
  end

  def +(other)
    __limit_result(__add(__operand(other), 1), 0)
  end

  def -(other)
    __limit_result(__add(__operand(other), -1), 0)
  end

  def *(other)
    __limit_result(__mult(__operand(other)), 0)
  end

  def /(other)
    other = __operand(other)
    special = __divide_special(other)
    return special if special
    digits = [n_significant_digits, other.n_significant_digits, DOUBLE_FIG].max + DOUBLE_FIG
    limit = BigDecimal.__limit_now
    digits = limit if limit > 0 && limit < digits
    __quotient(other, digits)
  end
  alias quo /

  def div(other, digits = nil)
    if digits.nil?
      other = __operand(other)
      raise ZeroDivisionError, "divided by 0" if other.zero?
      raise FloatDomainError, "Computation results in 'NaN' (Not a Number)" if nan? || other.nan?
      raise FloatDomainError, "Computation results in 'Infinity'" if infinite?
      return 0 if other.infinite?
      return (to_r / other.to_r).floor
    end
    digits = Integer(digits)
    raise ArgumentError, "negative precision" if digits < 0
    return self / other if digits == 0
    other = __operand(other)
    special = __divide_special(other)
    return special if special
    __quotient(other, digits)
  end

  def %(other)
    other = __operand(other)
    return BigDecimal.__nan if nan? || other.nan? || infinite? || other.zero?
    return self if other.infinite? && (zero? || (@__sign == other.__sign))
    return other if other.infinite?
    quotient = (to_r / other.to_r).floor
    self - other * quotient
  end
  alias modulo %

  def remainder(other)
    other = __operand(other)
    return BigDecimal.__nan if nan? || other.nan? || infinite? || other.zero?
    return self if other.infinite?
    quotient = (to_r / other.to_r).truncate
    self - other * quotient
  end

  def divmod(other)
    other = __operand(other)
    if nan? || other.nan? || infinite? || other.zero?
      return [BigDecimal.__nan, BigDecimal.__nan]
    end
    quotient = (to_r / other.to_r).floor
    [BigDecimal(quotient), self - other * quotient]
  end

  # Comparison

  def <=>(other)
    return nil if nan?
    case other
    when BigDecimal
      return nil if other.nan?
    when Integer, Rational
    when Float
      return nil if other.nan?
    else
      return __coerced_compare(other)
    end
    other = BigDecimal.__coerce(other, n_significant_digits + DOUBLE_FIG) unless other.is_a?(BigDecimal) || other.is_a?(Rational)
    if other.is_a?(Rational)
      return @__sign <=> 0 if infinite?
      return to_r <=> other
    end
    if infinite? || other.infinite?
      mine = infinite? ? @__sign * 2 : 0
      theirs = other.infinite? ? other.infinite? * 2 : 0
      return mine <=> theirs if mine != theirs
      return 0 if mine != 0
    end
    to_r <=> other.to_r
  end

  def ==(other)
    return false if nan?
    result = (self <=> other) rescue nil
    result == 0
  end
  alias === ==
  alias eql? ==

  def <(other)
    __compare(other, :<) { |c| c < 0 }
  end

  def <=(other)
    __compare(other, :<=) { |c| c <= 0 }
  end

  def >(other)
    __compare(other, :>) { |c| c > 0 }
  end

  def >=(other)
    __compare(other, :>=) { |c| c >= 0 }
  end

  # Rounding

  def round(*args, half: nil)
    digits = args[0]
    mode = args[1]
    if digits.is_a?(Symbol) || digits.is_a?(String)
      mode = digits
      digits = nil
    end
    mode = if half
             case half
             when :up, "up" then ROUND_HALF_UP
             when :down, "down" then ROUND_HALF_DOWN
             when :even, "even" then ROUND_HALF_EVEN
             when nil then BigDecimal.__rounding_mode_now
             else raise ArgumentError, "invalid rounding mode (#{half.inspect})"
             end
           elsif mode
             BigDecimal.__rounding_mode(mode)
           else
             BigDecimal.__rounding_mode_now
           end
    if args.empty?
      __check_finite_for_integer
      return __round_at(0, mode).to_i
    end
    __round_at(digits.nil? ? 0 : Integer(digits), mode)
  end

  def floor(digits = nil)
    if digits.nil?
      __check_finite_for_integer
      return __round_at(0, ROUND_FLOOR).to_i
    end
    __round_at(Integer(digits), ROUND_FLOOR)
  end

  def ceil(digits = nil)
    if digits.nil?
      __check_finite_for_integer
      return __round_at(0, ROUND_CEILING).to_i
    end
    __round_at(Integer(digits), ROUND_CEILING)
  end

  def truncate(digits = nil)
    if digits.nil?
      __check_finite_for_integer
      return to_i
    end
    __round_at(Integer(digits), ROUND_DOWN)
  end

  def fix
    return self unless finite?
    __round_at(0, ROUND_DOWN)
  end

  def frac
    return self unless finite?
    self - fix
  end

  def _decimal_shift(shift)
    return self unless finite? && @__coefficient != 0
    BigDecimal.__make(@__sign, @__coefficient, @__exponent + Integer(shift))
  end

  # The value rounded to digits significant digits by the rounding mode.
  def __round_significant(digits, mode = BigDecimal.__rounding_mode_now)
    return self unless finite? && @__coefficient != 0
    count = BigDecimal.__digit_count(@__coefficient)
    return self if count <= digits
    __round_at(-(count + @__exponent - digits), mode)
  end

  protected

  def __operand(other)
    BigDecimal.__coerce(other, [n_significant_digits, DOUBLE_FIG].max + DOUBLE_FIG)
  end

  private

  def __check_finite_for_integer(target = "Integer")
    raise FloatDomainError, "Computation results in 'NaN' (Not a Number)" if nan?
    if @__special == :infinity
      raise FloatDomainError, "Computation results in '#{@__sign < 0 ? "-" : ""}Infinity'"
    end
  end

  def __compare(other, operator)
    result = self <=> other
    if result.nil?
      return false if nan? || (other.respond_to?(:nan?) && other.nan?)
      raise ArgumentError, "comparison of BigDecimal with #{other.inspect} failed"
    end
    yield result
  end

  def __coerced_compare(other)
    return nil unless other.respond_to?(:coerce)
    a, b = other.coerce(self)
    a <=> b
  rescue StandardError
    nil
  end

  def __limit_result(value, digits)
    digits = Integer(digits)
    raise ArgumentError, "negative precision" if digits < 0
    limit = BigDecimal.__limit_now
    digits = limit if digits == 0 || (limit > 0 && limit < digits)
    digits > 0 ? value.__round_significant(digits) : value
  end

  def __add(other, sign)
    other_sign = other.__sign * sign
    if nan? || other.nan?
      return BigDecimal.__nan
    elsif infinite? || other.infinite?
      if infinite? && other.infinite?
        return @__sign == other_sign ? self : BigDecimal.__nan
      end
      return infinite? ? self : BigDecimal.__infinity(other_sign)
    end
    return BigDecimal.__build(other_sign, other.__coefficient, other.__exponent, nil) if zero? && !other.zero?
    if other.zero?
      return self unless zero?
      return BigDecimal.__zero(@__sign < 0 && other_sign < 0 ? -1 : 1)
    end
    exponent = [@__exponent, other.__exponent].min
    a = @__sign * @__coefficient * 10**(@__exponent - exponent)
    b = other_sign * other.__coefficient * 10**(other.__exponent - exponent)
    total = a + b
    return BigDecimal.__zero(1) if total == 0
    BigDecimal.__make(total < 0 ? -1 : 1, total.abs, exponent)
  end

  def __mult(other)
    sign = @__sign * other.__sign
    return BigDecimal.__nan if nan? || other.nan?
    if infinite? || other.infinite?
      return BigDecimal.__nan if zero? || other.zero?
      return BigDecimal.__infinity(sign)
    end
    return BigDecimal.__zero(sign) if zero? || other.zero?
    BigDecimal.__make(sign, @__coefficient * other.__coefficient, @__exponent + other.__exponent)
  end

  def __divide_special(other)
    sign = @__sign * other.__sign
    return BigDecimal.__nan if nan? || other.nan?
    if infinite?
      return BigDecimal.__nan if other.infinite?
      return BigDecimal.__infinity(sign)
    end
    return BigDecimal.__zero(sign) if other.infinite?
    if other.zero?
      if zero?
        if BigDecimal.__exception_mode_now & EXCEPTION_NaN != 0
          raise FloatDomainError, "Computation results in 'NaN' (Not a Number)"
        end
        return BigDecimal.__nan
      end
      if BigDecimal.__exception_mode_now & EXCEPTION_ZERODIVIDE != 0
        raise ZeroDivisionError, "divided by 0"
      end
      return BigDecimal.__infinity(sign)
    end
    return BigDecimal.__zero(sign) if zero?
    nil
  end

  # self / other rounded to digits significant digits.
  def __quotient(other, digits)
    sign = @__sign * other.__sign
    a = @__coefficient
    b = other.__coefficient
    shift = digits + BigDecimal.__digit_count(b) - BigDecimal.__digit_count(a) + 1
    shift = 0 if shift < 0
    quotient, remainder = (a * 10**shift).divmod(b)
    exponent = @__exponent - other.__exponent - shift
    BigDecimal.__rounded(sign, quotient, exponent, remainder != 0, digits, BigDecimal.__rounding_mode_now)
  end

  # Rounds to the given number of digits after the decimal point.
  def __round_at(position, mode)
    return self unless finite?
    return self if @__coefficient == 0 || @__exponent >= -position
    drop = -position - @__exponent
    count = BigDecimal.__digit_count(@__coefficient)
    BigDecimal.__rounded(@__sign, @__coefficient, @__exponent, false, count - drop, mode)
  end

  # sign * coefficient * 10**exponent (plus a nonzero tail when sticky),
  # rounded to keep digits significant digits (none or fewer: to zero or
  # one unit in that place).
  def self.__rounded(sign, coefficient, exponent, sticky, digits, mode)
    count = __digit_count(coefficient)
    drop = count - digits
    if drop <= 0
      return __make(sign, coefficient, exponent) unless sticky
      drop = 0
    end
    unit = 10**drop
    kept, rest = coefficient.divmod(unit)
    half = unit / 2
    exact_half = drop > 0 && rest == half && !sticky
    above_half = drop > 0 ? (rest > half || (rest == half && sticky)) : false
    nonzero = rest != 0 || sticky
    round_up = case mode
               when ROUND_UP then nonzero
               when ROUND_DOWN then false
               when ROUND_HALF_UP then above_half || exact_half
               when ROUND_HALF_DOWN then above_half
               when ROUND_HALF_EVEN then above_half || (exact_half && kept.odd?)
               when ROUND_CEILING then nonzero && sign > 0
               when ROUND_FLOOR then nonzero && sign < 0
               end
    kept += 1 if round_up
    return __zero(sign) if kept == 0
    __make(sign, kept, exponent + drop)
  end
end

module Kernel
  def BigDecimal(value, digits = nil, exception: true)
    unless digits.nil?
      digits = Integer(digits)
      raise ArgumentError, "negative precision" if digits < 0
    end
    BigDecimal.__convert(value, digits, exception)
  rescue ArgumentError, TypeError
    raise if exception
    nil
  end
  private :BigDecimal
  module_function :BigDecimal
end

class BigDecimal
  INFINITY = __infinity(1)
  NAN = __nan
end
