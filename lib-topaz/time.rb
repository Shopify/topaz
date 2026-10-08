# Time, in Ruby over an integer count of nanoseconds since the epoch
# (@ns). A time is in UTC (@utc), at a fixed offset (@off, seconds east of
# UTC), or local (both unset). Civil fields use the proleptic Gregorian
# calendar.
class Time
  include Comparable

  NS = 1_000_000_000

  class << self
    def now(**opts)
      t = __topaz_new((__topaz_now_float * NS).round)
      zone = opts[:in]
      zone ? t.localtime(zone) : t
    end

    def at(time, subsec = nil, unit = :microsecond, **opts)
      ns = case time
           when Time then time.__topaz_ns
           when Integer then time * NS
           when Float then (time * NS).round
           when Rational then (time * NS).floor
           when Numeric then (time.to_r * NS).floor
           else raise TypeError, "can't convert #{time.class} into an exact number"
           end
      if subsec
        factor = case unit
                 when :millisecond then 1_000_000
                 when :usec, :microsecond then 1000
                 when :nsec, :nanosecond then 1
                 else raise ArgumentError, "unexpected unit: #{unit}"
                 end
        ns += __topaz_scaled_floor(subsec, factor)
      end
      t = __topaz_new(ns)
      if time.is_a?(Time)
        t.__send__(:__topaz_set_zone, time.utc?, time.__topaz_fixed_offset)
      end
      zone = opts[:in]
      zone ? t.localtime(zone) : t
    end

    # value * factor truncated towards -Infinity, as MRI does for the
    # sub-second argument of Time.at; Floats are converted exactly first.
    def __topaz_scaled_floor(value, factor)
      case value
      when Integer then value * factor
      when Rational then (value.numerator * factor).div(value.denominator)
      when Numeric
        r = value.to_r
        (r.numerator * factor).div(r.denominator)
      else raise TypeError, "can't convert #{value.class} into an exact number"
      end
    end
    private :__topaz_scaled_floor

    def utc(*args)
      t = __topaz_new(__topaz_civil_ns(*args))
      t.utc
    end
    alias gm utc

    def local(*args)
      utc_ns = __topaz_civil_ns(*args)
      t = __topaz_new(utc_ns - __topaz_local_offset_for_wall(utc_ns.div(NS)) * NS)
      t
    end
    alias mktime local

    def new(year = nil, mon = nil, day = nil, hour = nil, min = nil, sec = nil, zone = nil, **opts)
      zone ||= opts[:in]
      return now(in: zone) if year.nil?
      if year.is_a?(String) && mon.nil?
        return __topaz_parse_new(year, zone)
      end
      utc_ns = __topaz_civil_ns(year, mon || 1, day || 1, hour || 0, min || 0, sec || 0)
      if zone.nil?
        __topaz_new(utc_ns - __topaz_local_offset_for_wall(utc_ns.div(NS)) * NS)
      elsif __topaz_utc_zone?(zone)
        __topaz_new(utc_ns).utc
      else
        offset = __topaz_offset(zone)
        t = __topaz_new(utc_ns - offset * NS)
        t.__send__(:__topaz_set_zone, false, offset)
        t
      end
    end

    def __topaz_new(ns)
      t = allocate
      t.__send__(:__topaz_init, ns)
      t
    end

    # Nanoseconds since the epoch of a civil time taken as UTC.
    def __topaz_civil_ns(*args)
      if args.size == 10
        sec, min, hour, day, mon, year = args
        usec = 0
      else
        year, mon, day, hour, min, sec, usec = args
      end
      year = Topaz.convert_type(year, Integer, :to_int) unless year.is_a?(Integer)
      mon = __topaz_month(mon || 1)
      day = (day || 1).to_i
      hour = (hour || 0).to_i
      min = (min || 0).to_i
      sec ||= 0
      sec = sec.to_r if sec.is_a?(String)
      raise ArgumentError, "mon out of range" unless (1..12).cover?(mon)
      raise ArgumentError, "argument out of range" unless (1..31).cover?(day)
      raise ArgumentError, "argument out of range" unless (0..24).cover?(hour)
      raise ArgumentError, "argument out of range" unless (0..59).cover?(min)
      raise ArgumentError, "argument out of range" unless sec >= 0 && sec < 61
      last = __topaz_days_in_month(year, mon)
      if day > last
        # Time.utc(2023, 2, 30) is March 2nd, as in CRuby.
        extra = day - last
        day = last
      else
        extra = 0
      end
      days = __topaz_days_from_civil(year, mon, day) + extra
      whole_sec = sec.floor
      ns = ((days * 86400 + hour * 3600 + min * 60 + whole_sec) * NS)
      ns += ((sec - whole_sec) * NS).round
      ns += (usec.to_r * 1000).round if usec
      ns
    end

    def __topaz_month(mon)
      if mon.is_a?(String)
        i = Topaz::Strftime::MONTHNAMES.index { |n| n && n[0, 3].downcase == mon.downcase }
        return i if i
        mon = mon.to_i
      end
      mon.to_i
    end

    def __topaz_days_in_month(y, m)
      return 29 if m == 2 && (y % 4 == 0 && (y % 100 != 0 || y % 400 == 0))
      [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m]
    end

    # Days since 1970-01-01 of a proleptic Gregorian date.
    def __topaz_days_from_civil(y, m, d)
      y -= 1 if m <= 2
      era = y.div(400)
      yoe = y - era * 400
      doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1
      doe = yoe * 365 + yoe / 4 - yoe / 100 + doy
      era * 146097 + doe - 719468
    end

    # [year, month, day] of a count of days since 1970-01-01.
    def __topaz_civil_from_days(z)
      z += 719468
      era = z.div(146097)
      doe = z - era * 146097
      yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365
      y = yoe + era * 400
      doy = doe - (365 * yoe + yoe / 4 - yoe / 100)
      mp = (5 * doy + 2) / 153
      d = doy - (153 * mp + 2) / 5 + 1
      m = mp + (mp < 10 ? 3 : -9)
      [m <= 2 ? y + 1 : y, m, d]
    end

    def __topaz_local_offset(seconds)
      __topaz_local_zone(seconds)[0]
    rescue RangeError
      0
    end

    # The local offset for a wall-clock time given as if it were UTC.
    def __topaz_local_offset_for_wall(wall_seconds)
      offset = __topaz_local_offset(wall_seconds)
      __topaz_local_offset(wall_seconds - offset)
    end

    def __topaz_utc_zone?(zone)
      zone.is_a?(String) && (zone == "UTC" || zone == "Z" || zone == "-00:00")
    end

    def __topaz_offset(zone)
      case zone
      when Integer then zone
      when Rational, Float then zone.round
      when String
        if (m = zone.match(/\A([-+])(\d{2}):?(\d{2})(?::?(\d{2}))?\z/))
          s = m[2].to_i * 3600 + m[3].to_i * 60 + m[4].to_i
          m[1] == "-" ? -s : s
        elsif __topaz_utc_zone?(zone)
          0
        elsif zone =~ /\A[A-I]|[K-Z]\z/ && zone.size == 1
          # Military zones.
          c = zone.ord
          c = c - 64 if c <= 73
          c = c - 65 if c >= 75 && c <= 77
          c <= 12 ? c * 3600 : -(c - 13 + 1) * 3600
        else
          raise ArgumentError, %("+HH:MM", "-HH:MM", "UTC" or "A".."I","K".."Z" expected for utc_offset: #{zone})
        end
      else
        if zone.respond_to?(:utc_to_local)
          zone
        else
          raise TypeError, "can't convert #{zone.class} into an exact number"
        end
      end
    end

    def __topaz_parse_new(string, zone)
      m = string.match(/\A\s*(-?\d{4,})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?)?\s*(Z|UTC|[-+]\d{2}:?\d{2})?\s*\z/)
      raise ArgumentError, "can't parse: #{string.inspect}" unless m
      sec = m[6].to_i
      sec = sec + Rational(m[7].to_i, 10**m[7].size) if m[7]
      new(m[1].to_i, m[2].to_i, m[3].to_i, m[4].to_i, m[5].to_i, sec, m[8] || zone)
    end
  end

  def __topaz_ns
    @ns
  end

  def __topaz_fixed_offset
    @off
  end

  def initialize_copy(other)
    super
    @ns = other.__topaz_ns
    @utc = other.utc?
    @off = other.__topaz_fixed_offset
    @fields = nil
    self
  end

  # Conversions

  def to_i
    @ns.div(NS)
  end
  alias tv_sec to_i

  def to_f
    @ns.fdiv(NS)
  end

  def to_r
    Rational(@ns, NS)
  end

  def usec
    @ns % NS / 1000
  end
  alias tv_usec usec

  def nsec
    @ns % NS
  end
  alias tv_nsec nsec

  def subsec
    Rational(@ns % NS, NS)
  end

  def to_time
    self
  end

  def to_a
    [sec, min, hour, day, month, year, wday, yday, dst?, zone]
  end

  # Zones

  def utc?
    @utc ? true : false
  end
  alias gmt? utc?

  def utc_offset
    return 0 if @utc
    return @off if @off.is_a?(Integer)
    Time.__topaz_local_offset(to_i)
  end
  alias gmt_offset utc_offset
  alias gmtoff utc_offset

  def zone
    return "UTC" if @utc
    return nil if @off
    Time.__topaz_local_zone(to_i)[1]
  rescue RangeError
    nil
  end

  def dst?
    false
  end
  alias isdst dst?

  def utc
    __topaz_set_zone(true, nil)
    self
  end
  alias gmtime utc

  def getutc
    dup.utc
  end
  alias getgm getutc

  def localtime(offset = nil)
    if offset.nil?
      __topaz_set_zone(false, nil)
    elsif Time.__topaz_utc_zone?(offset)
      __topaz_set_zone(true, nil)
    else
      __topaz_set_zone(false, Time.__topaz_offset(offset))
    end
    self
  end

  def getlocal(offset = nil)
    dup.localtime(offset)
  end

  # Civil fields

  def year
    __topaz_fields[0]
  end

  def month
    __topaz_fields[1]
  end
  alias mon month

  def day
    __topaz_fields[2]
  end
  alias mday day

  def hour
    __topaz_fields[3]
  end

  def min
    __topaz_fields[4]
  end

  def sec
    __topaz_fields[5]
  end

  def wday
    __topaz_fields[6]
  end

  def yday
    __topaz_fields[7]
  end

  %w[sunday monday tuesday wednesday thursday friday saturday].each_with_index do |name, i|
    define_method("#{name}?") { wday == i }
  end

  # ISO 8601 week-based year and week, for strftime.
  def cwyear
    __topaz_commercial[0]
  end

  def cweek
    __topaz_commercial[1]
  end

  # Arithmetic and comparison

  def +(other)
    raise TypeError, "time + time?" if other.is_a?(Time)
    __topaz_with_ns(@ns + __topaz_ns_of(other))
  end

  def -(other)
    if other.is_a?(Time)
      return (@ns - other.__topaz_ns).fdiv(NS)
    end
    __topaz_with_ns(@ns - __topaz_ns_of(other))
  end

  def succ
    self + 1
  end

  def <=>(other)
    if other.is_a?(Time)
      @ns <=> other.__topaz_ns
    elsif other.respond_to?(:to_time) && !other.is_a?(Numeric)
      @ns <=> other.to_time.__topaz_ns
    end
  end

  def eql?(other)
    other.is_a?(Time) && @ns == other.__topaz_ns
  end

  def hash
    @ns.hash ^ 0x5a5a
  end

  def round(digits = 0)
    unit = 10**(9 - digits)
    return dup if digits >= 9
    rem = @ns % unit
    __topaz_with_ns(rem * 2 >= unit ? @ns - rem + unit : @ns - rem)
  end

  def floor(digits = 0)
    return dup if digits >= 9
    unit = 10**(9 - digits)
    __topaz_with_ns(@ns - @ns % unit)
  end

  def ceil(digits = 0)
    return dup if digits >= 9
    unit = 10**(9 - digits)
    rem = @ns % unit
    __topaz_with_ns(rem == 0 ? @ns : @ns - rem + unit)
  end

  # Formatting

  def strftime(format)
    Topaz::Strftime.format(self, format)
  end

  def to_s
    utc? ? strftime("%Y-%m-%d %H:%M:%S UTC") : strftime("%Y-%m-%d %H:%M:%S %z")
  end

  def inspect
    s = strftime("%Y-%m-%d %H:%M:%S")
    fraction = @ns % NS
    if fraction != 0
      digits = fraction.to_s.rjust(9, "0").sub(/0+\z/, "")
      s << "." << digits
    end
    s << (utc? ? " UTC" : strftime(" %z"))
  end

  def asctime
    strftime("%a %b %e %T %Y")
  end
  alias ctime asctime

  def iso8601(fraction_digits = 0)
    s = strftime("%Y-%m-%dT%H:%M:%S")
    s << "." << strftime("%#{fraction_digits}N") if fraction_digits > 0
    s << (utc? ? "Z" : strftime("%:z"))
  end
  alias xmlschema iso8601

  def deconstruct_keys(keys)
    h = {year: year, month: month, day: day, yday: yday, wday: wday, hour: hour,
         min: min, sec: sec, subsec: subsec, dst: dst?, zone: zone}
    keys ? h.slice(*keys) : h
  end

  def _dump(limit = -1)
    [@ns, @utc ? 1 : 0, @off || 0, @off ? 1 : 0].join(",")
  end

  def self._load(string)
    ns, utc, off, fixed = string.split(",").map(&:to_i)
    t = __topaz_new(ns)
    t.__send__(:__topaz_set_zone, utc == 1, fixed == 1 ? off : nil)
    t
  end

  # For Topaz::Strftime.

  def __topaz_nanoseconds
    nsec
  end

  def __topaz_utc_offset
    utc_offset
  end

  def __topaz_epoch_seconds
    to_r
  end

  private

  def __topaz_init(ns)
    @ns = ns
    @utc = false
    @off = nil
    @fields = nil
  end

  def __topaz_set_zone(utc, offset)
    @utc = utc
    @off = offset
    @fields = nil
  end

  def __topaz_with_ns(ns)
    t = self.class.__topaz_new(ns)
    t.__send__(:__topaz_set_zone, @utc, @off)
    t
  end

  def __topaz_ns_of(value)
    case value
    when Integer then value * NS
    when Float then (value * NS).round
    when Rational then (value * NS).round
    when Numeric then (value.to_r * NS).round
    else raise TypeError, "can't convert #{value.class} into an exact number"
    end
  end

  def __topaz_fields
    @fields ||= begin
      local = to_i + utc_offset
      days = local.div(86400)
      secs = local % 86400
      y, m, d = Time.__topaz_civil_from_days(days)
      wday = (days + 4) % 7
      yday = days - Time.__topaz_days_from_civil(y, 1, 1) + 1
      [y, m, d, secs / 3600, secs % 3600 / 60, secs % 60, wday, yday]
    end
  end

  def __topaz_commercial
    y = year
    wd = wday == 0 ? 7 : wday
    week = (yday - wd + 10) / 7
    if week < 1
      y -= 1
      dec31 = Time.utc(y, 12, 31)
      week = (dec31.yday - (dec31.wday == 0 ? 7 : dec31.wday) + 10) / 7
    elsif week > 52
      jan1_next_wday = (Time.__topaz_days_from_civil(y + 1, 1, 1) + 4) % 7
      jan1_next_wday = 7 if jan1_next_wday == 0
      if jan1_next_wday <= 4
        y += 1
        week = 1
      end
    end
    [y, week]
  end
end
