class Random
  def self.bytes(n)
    DEFAULT.bytes(n)
  end

  def self.urandom(n)
    n = Topaz.convert_type(n, Integer, :to_int)
    raise ArgumentError, "negative string size (or size too big)" if n < 0
    return "" if n == 0
    # One open file for the process: SecureRandom asks for a few bytes per
    # request id, token and uuid, and opening the device each time cost
    # more than reading it.
    f = @__topaz_urandom ||= File.open("/dev/urandom", "rb")
    f.read(n).force_encoding(Encoding::BINARY)
  rescue IOError, SystemCallError
    @__topaz_urandom = nil
    File.open("/dev/urandom", "rb") { |f| f.read(n) }
  end

  def self.raw_seed(n)
    urandom(n)
  end

  def self.new_seed
    seed = 0
    urandom(16).each_byte { |b| seed = (seed << 8) | b }
    seed
  end

  def self.seed
    DEFAULT.seed
  end

  def self.random_number(n = 0)
    DEFAULT.random_number(n)
  end

  # Random::Formatter builds on #bytes; random/formatter.rb adds hex,
  # base64, uuid and friends on top of these.
  module Formatter
    def random_number(n = 0)
      __random_value(n, false)
    end

    def rand(n = 0)
      __random_value(n, true)
    end

    private

    def __random_float
      v = 0
      bytes(7).each_byte { |b| v = (v << 8) | b }
      (v >> 3) * (1.0 / 9007199254740992)
    end

    def __random_integer(n)
      return 0 if n <= 1
      bits = (n - 1).bit_length
      nbytes = (bits + 7) / 8
      mask = (1 << bits) - 1
      loop do
        v = 0
        bytes(nbytes).each_byte { |b| v = (v << 8) | b }
        v &= mask
        return v if v < n
      end
    end

    def __random_value(n, strict)
      case n
      when nil
        __random_float
      when Integer
        return __random_integer(n) if n > 0
        return __random_float if n == 0 || !strict
        raise ArgumentError, "invalid argument - #{n}"
      when Float
        return __random_float * n if n > 0
        return __random_float if n == 0 || !strict
        raise ArgumentError, "invalid argument - #{n}"
      when Range
        first = n.begin
        last = n.end
        if first.is_a?(Integer) && last.is_a?(Integer)
          last -= 1 if n.exclude_end?
          return nil if last < first
          first + __random_integer(last - first + 1)
        else
          first + __random_float * (last - first)
        end
      else
        raise ArgumentError, "invalid argument - #{n.inspect}" if strict
        __random_float
      end
    end
  end

  include Formatter

  # Random's own rand is the builtin one; Formatter#rand is for objects
  # that only provide #bytes, like SecureRandom.
  def random_number(n = 0)
    n.nil? || n == 0 || (n.is_a?(Numeric) && n < 0) ? rand : rand(n)
  end
end
