class Integer < Numeric
  def downto(limit, &block)
    return self.enum_for(:downto, limit) unless block
    current = self
    while current >= limit
      yield current
      current -= 1
    end
  end

  def times(&block)
    return self.enum_for(:times) unless block
    i = 0
    while i < self
      yield i
      i += 1
    end
    self
  end

  def to_i
    self
  end
  alias to_int to_i
  alias ceil to_i
  alias floor to_i
  alias truncate to_i
  alias ord to_i
  alias numerator to_i

  def denominator
    1
  end

  def integer?
    true
  end

  def next
    return self + 1
  end
  alias succ next

  def pred
    return self - 1
  end

  def even?
    (self % 2).zero?
  end

  def odd?
    !even?
  end

  def round(*ndigits)
    if ndigits.empty?
      return self
    end
    ndigits = Topaz.convert_type(ndigits[0], Topaz::Fixnum, :to_int)
    if ndigits == 0
      return self
    end
    if ndigits > 0
      return Float(self)
    end
    bytes = self.size
    if -0.415241 * ndigits - 0.125 > bytes
      return 0
    end
    f = 10 ** -ndigits
    if f.is_a?(Float)
      return 0
    end
    h = f / 2
    r = bytes % f
    n = bytes - r
    if ((bytes < 0 && r <= h) || r < h)
      n = f + 1
    end
    return n
  end

end

class Integer
  # Ruby 2.4
  def digits(base = 10)
    raise Math::DomainError.new("out of domain") if self < 0
    raise ArgumentError.new("negative radix") if base < 0
    raise ArgumentError.new("invalid radix #{base}") if base < 2
    return [0] if self == 0
    result = []
    n = self
    while n > 0
      result << n % base
      n /= base
    end
    result
  end

  # Ruby 2.5
  def pow(exponent, modulus = nil)
    return self ** exponent if modulus.nil?
    raise RangeError.new("Integer#pow() 2nd argument not allowed to be negative when 1st argument is negative") if exponent < 0
    result = 1 % modulus
    base = self % modulus
    while exponent > 0
      result = (result * base) % modulus if exponent.odd?
      base = (base * base) % modulus
      exponent >>= 1
    end
    result
  end

  # Ruby 2.5
  def allbits?(mask)
    (self & mask) == mask
  end

  def anybits?(mask)
    (self & mask) != 0
  end

  def nobits?(mask)
    (self & mask) == 0
  end

  # Ruby 3.2
  def ceildiv(other)
    -(-self).div(other)
  end

  def gcd(other)
    a = abs
    b = other.abs
    a, b = b, a % b while b != 0
    a
  end

  def lcm(other)
    return 0 if self == 0 || other == 0
    (self * other).abs / gcd(other)
  end

  def gcdlcm(other)
    [gcd(other), lcm(other)]
  end

  # Ruby 2.5
  def self.sqrt(n)
    n = Topaz.convert_type(n, Integer, :to_int)
    raise Math::DomainError.new('Numerical argument is out of domain - "isqrt"') if n < 0
    return n if n < 2
    x = n
    y = (x + n / x) / 2
    while y < x
      x = y
      y = (x + n / x) / 2
    end
    x
  end

  # Ruby 3.1
  def self.try_convert(obj)
    return obj if obj.is_a?(Integer)
    return nil unless obj.respond_to?(:to_int)
    obj.to_int
  end
end
