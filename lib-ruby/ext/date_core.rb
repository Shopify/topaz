# Replaces CRuby's date_core C extension: Date and DateTime in Ruby.
#
# A date is a chronological Julian Day Number (@jd) and the day the
# Gregorian calendar starts (@sg); a DateTime adds seconds into the UTC day
# (@df), a fraction of a second (@sf, Rational) and a UTC offset in
# seconds (@of). Civil dates before @sg are Julian.
class Date
  include Comparable

  ITALY = 2299161
  ENGLAND = 2361222
  JULIAN = Float::INFINITY
  GREGORIAN = -Float::INFINITY

  MONTHNAMES = [nil, "January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"].freeze
  ABBR_MONTHNAMES = [nil, "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
                     "Sep", "Oct", "Nov", "Dec"].freeze
  DAYNAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
              "Saturday"].freeze
  ABBR_DAYNAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].freeze

  class Error < ArgumentError
  end

  # Calendar arithmetic, on integers.
  module Calendar
    module_function

    def civil_to_jd(y, m, d, sg)
      if m <= 2
        y -= 1
        m += 12
      end
      a = y.div(100)
      b = 2 - a + a.div(4)
      jd = (1461 * (y + 4716)).div(4) + (306001 * (m + 1)).div(10000) + d + b - 1524
      jd -= b if jd < sg
      jd
    end

    def jd_to_civil(jd, sg)
      if jd < sg
        a = jd
      else
        x = (4 * jd - 7468865).div(146097)
        a = jd + 1 + x - x.div(4)
      end
      b = a + 1524
      c = (20 * b - 2442).div(7305)
      d = (1461 * c).div(4)
      e = (10000 * (b - d)).div(306001)
      dom = b - d - (306001 * e).div(10000)
      if e <= 13
        m = e - 1
        y = c - 4716
      else
        m = e - 13
        y = c - 4715
      end
      [y, m, dom]
    end

    def gregorian_leap?(y)
      (y % 4 == 0 && y % 100 != 0) || y % 400 == 0
    end

    def julian_leap?(y)
      y % 4 == 0
    end

    def days_in_month(y, m, sg)
      nm_y, nm_m = m == 12 ? [y + 1, 1] : [y, m + 1]
      civil_to_jd(nm_y, nm_m, 1, sg) - civil_to_jd(y, m, 1, sg)
    end

    # The JD of y-m-d, allowing negative months and days counted from the
    # end, or nil if there is no such date.
    def valid_civil(y, m, d, sg)
      m += 13 if m < 0
      return nil if m < 1 || m > 12
      if d < 0
        last = days_in_month(y, m, sg)
        d = last + d + 1
        return nil if d < 1
      end
      return nil if d < 1
      jd = civil_to_jd(y, m, d, sg)
      return nil unless jd_to_civil(jd, sg) == [y, m, d]
      jd
    end

    def valid_ordinal(y, yday, sg)
      first = civil_to_jd(y, 1, 1, sg)
      days = civil_to_jd(y + 1, 1, 1, sg) - first
      yday = days + yday + 1 if yday < 0
      return nil if yday < 1 || yday > days
      first + yday - 1
    end

    # ISO 8601 week dates.
    def jd_to_commercial(jd, sg)
      y = jd_to_civil(jd - 3, sg)[0]
      week1 = commercial_week1(y + 1, sg)
      if jd >= week1
        y += 1
      else
        week1 = commercial_week1(y, sg)
      end
      w = (jd - week1).div(7) + 1
      d = (jd + 1) % 7
      d = 7 if d == 0
      [y, w, d]
    end

    # The JD of the Monday of week 1 of ISO year y.
    def commercial_week1(y, sg)
      jan4 = civil_to_jd(y, 1, 4, sg)
      wday = (jan4 + 1) % 7
      wday = 7 if wday == 0
      jan4 - (wday - 1)
    end

    def valid_commercial(y, w, d, sg)
      d += 8 if d < 0
      return nil if d < 1 || d > 7
      if w < 0
        next_week1 = commercial_week1(y + 1, sg)
        w = (next_week1 - commercial_week1(y, sg)).div(7) + w + 1
      end
      jd = commercial_week1(y, sg) + 7 * (w - 1) + (d - 1)
      return nil unless jd_to_commercial(jd, sg) == [y, w, d]
      jd
    end
  end

  class << self
    def valid_jd?(jd, start = ITALY)
      jd.is_a?(Numeric)
    end

    def valid_civil?(y, m, d, start = ITALY)
      !Calendar.valid_civil(y, m, d, start).nil?
    end
    alias valid_date? valid_civil?

    def valid_ordinal?(y, yday, start = ITALY)
      !Calendar.valid_ordinal(y, yday, start).nil?
    end

    def valid_commercial?(y, w, d, start = ITALY)
      !Calendar.valid_commercial(y, w, d, start).nil?
    end

    def gregorian_leap?(y)
      Calendar.gregorian_leap?(y)
    end
    alias leap? gregorian_leap?

    def julian_leap?(y)
      Calendar.julian_leap?(y)
    end

    def jd(jd = 0, start = ITALY)
      __topaz_from_jd(jd.floor, start, jd - jd.floor)
    end

    def civil(y = -4712, m = 1, d = 1, start = ITALY)
      jd = Calendar.valid_civil(y, m, d.floor, start)
      raise Date::Error, "invalid date" if jd.nil?
      __topaz_from_jd(jd, start, d - d.floor)
    end

    def ordinal(y = -4712, yday = 1, start = ITALY)
      jd = Calendar.valid_ordinal(y, yday, start)
      raise Date::Error, "invalid date" if jd.nil?
      __topaz_from_jd(jd, start)
    end

    def commercial(y = -4712, w = 1, d = 1, start = ITALY)
      jd = Calendar.valid_commercial(y, w, d, start)
      raise Date::Error, "invalid date" if jd.nil?
      __topaz_from_jd(jd, start)
    end

    def today(start = ITALY)
      t = Time.now
      civil(t.year, t.month, t.day, start)
    end

    def _parse(string, comp = true, limit: 128)
      Topaz::DateParser.parse(string, comp)
    end

    def parse(string = "-4712-01-01", comp = true, start = ITALY, limit: 128)
      __topaz_from_hash(_parse(string, comp), start)
    end

    def _strptime(string, format = "%F")
      Topaz::DateParser.strptime(string, format)
    end

    def strptime(string = "-4712-01-01", format = "%F", start = ITALY)
      hash = _strptime(string, format)
      raise Date::Error, "invalid date" if hash.nil? || hash[:leftover]
      __topaz_from_hash(hash, start)
    end

    %w[iso8601 rfc3339 xmlschema rfc2822 rfc822 httpdate jisx0301].each do |name|
      define_method("_#{name}") do |string, limit: 128|
        Topaz::DateParser.parse(string, true)
      end
      define_method(name) do |string = "-4712-01-01", start = ITALY, limit: 128|
        __topaz_from_hash(Topaz::DateParser.parse(string, true), start)
      end
    end

    def _load(string)
      jd, df, sf, of, sg = Marshal.load(string)
      __topaz_from_jd(jd, sg)
    end

    def __topaz_from_jd(jd, start, fraction = 0)
      date = allocate
      date.__send__(:__topaz_init, jd, start, fraction)
      date
    end

    def __topaz_from_hash(hash, start)
      raise Date::Error, "invalid date" if hash.nil? || hash.empty?
      if hash[:jd]
        return jd(hash[:jd], start)
      end
      if hash[:yday] && hash[:year] && !hash[:mon]
        return ordinal(hash[:year], hash[:yday], start)
      end
      if hash[:cwyear] && hash[:cweek]
        return commercial(hash[:cwyear], hash[:cweek], hash[:cwday] || 1, start)
      end
      if hash[:seconds]
        return jd(2440588 + hash[:seconds].div(86400), start)
      end
      today = nil
      year = hash[:year] || (today ||= Date.today).year
      mon = hash[:mon] || (hash[:year] ? 1 : (today ||= Date.today).mon)
      mday = hash[:mday] || (hash[:mon] ? 1 : (hash[:wday] ? nil : (today ||= Date.today).mday))
      if mday.nil? && hash[:wday]
        base = today || Date.today
        return base + (hash[:wday] - base.wday)
      end
      civil(year, mon, mday || 1, start)
    end
  end

  def initialize(y = -4712, m = 1, d = 1, start = ITALY)
    jd = Calendar.valid_civil(y, m, d, start)
    raise Date::Error, "invalid date" if jd.nil?
    __topaz_init(jd, start)
  end

  def jd
    @jd
  end

  def ajd
    Rational(@jd * 2 - 1, 2) + day_fraction - Rational(offset * 86400, 86400)
  end

  def amjd
    ajd - Rational(4800001, 2)
  end

  def mjd
    @jd - 2400001
  end

  def ld
    @jd - 2299160
  end

  def day_fraction
    0r
  end

  def start
    @sg
  end

  def new_start(start = ITALY)
    self.class.__topaz_from_jd(@jd, start)
  end

  def gregorian
    new_start(GREGORIAN)
  end

  def julian
    new_start(JULIAN)
  end

  def italy
    new_start(ITALY)
  end

  def england
    new_start(ENGLAND)
  end

  def gregorian?
    @jd >= @sg
  end

  def julian?
    !gregorian?
  end

  def year
    __topaz_civil[0]
  end

  def mon
    __topaz_civil[1]
  end
  alias month mon

  def mday
    __topaz_civil[2]
  end
  alias day mday

  def wday
    (@jd + 1) % 7
  end

  def yday
    @jd - Calendar.civil_to_jd(year, 1, 1, @sg) + 1
  end

  def cwyear
    Calendar.jd_to_commercial(@jd, @sg)[0]
  end

  def cweek
    Calendar.jd_to_commercial(@jd, @sg)[1]
  end

  def cwday
    w = wday
    w == 0 ? 7 : w
  end

  DAYNAMES.each_with_index do |name, i|
    define_method("#{name.downcase}?") { wday == i }
  end

  def leap?
    y = year
    gregorian? ? Calendar.gregorian_leap?(y) : Calendar.julian_leap?(y)
  end

  def hour
    0
  end

  def minute
    0
  end
  alias min minute

  def second
    0
  end
  alias sec second

  def second_fraction
    0r
  end
  alias sec_fraction second_fraction

  def offset
    0r
  end

  def zone
    "+00:00"
  end

  def +(other)
    case other
    when Integer
      __topaz_with_jd(@jd + other)
    when Rational, Float
      whole = other.floor
      __topaz_with_jd(@jd + whole, other - whole)
    when Numeric
      self + other.to_r
    else
      raise TypeError, "expected numeric"
    end
  end

  def -(other)
    case other
    when Date
      (ajd - other.ajd).rationalize(Rational(1, 10**18))
    when Numeric
      self + -other
    else
      raise TypeError, "expected numeric or date"
    end
  end

  def >>(n)
    raise TypeError, "expected numeric" unless n.is_a?(Numeric)
    y, m, d = __topaz_civil
    total = y * 12 + (m - 1) + n.to_i
    ny = total.div(12)
    nm = total % 12 + 1
    last = Calendar.days_in_month(ny, nm, @sg)
    d = last if d > last
    __topaz_with_jd(Calendar.civil_to_jd(ny, nm, d, @sg))
  end

  def <<(n)
    raise TypeError, "expected numeric" unless n.is_a?(Numeric)
    self >> -n
  end

  def next_day(n = 1)
    self + n
  end

  def prev_day(n = 1)
    self - n
  end

  def next_month(n = 1)
    self >> n
  end

  def prev_month(n = 1)
    self << n
  end

  def next_year(n = 1)
    self >> (n * 12)
  end

  def prev_year(n = 1)
    self << (n * 12)
  end

  def next
    next_day
  end
  alias succ next

  def step(limit, by = 1)
    return to_enum(:step, limit, by) unless block_given?
    raise ArgumentError, "step can't be 0" if by == 0
    d = self
    if by > 0
      while d <= limit
        yield d
        d += by
      end
    else
      while d >= limit
        yield d
        d += by
      end
    end
    self
  end

  def upto(max, &block)
    step(max, 1, &block)
  end

  def downto(min, &block)
    step(min, -1, &block)
  end

  def <=>(other)
    case other
    when Date
      ajd <=> other.ajd
    when Numeric
      ajd <=> other
    else
      # As with Numeric, let the other object coerce the comparison.
      return nil unless other.respond_to?(:coerce)
      begin
        a, b = other.coerce(self)
      rescue StandardError
        return nil
      end
      a <=> b
    end
  end

  def ==(other)
    return false unless other.is_a?(Date) || other.is_a?(Numeric)
    (self <=> other) == 0
  end

  def ===(other)
    case other
    when Date
      jd == other.jd
    when Numeric
      jd == other.to_i
    else
      false
    end
  end

  def eql?(other)
    other.is_a?(Date) && self == other
  end

  def hash
    ajd.hash
  end

  def to_s
    format("%.4d-%02d-%02d", year, mon, mday)
  end
  alias iso8601 to_s
  alias xmlschema to_s

  def inspect
    "#<#{self.class}: #{to_s} ((#{@jd}j,0s,0n),+0s,#{@sg.is_a?(Float) ? @sg : "#{@sg}j"})>"
  end

  def rfc3339
    strftime("%Y-%m-%dT%H:%M:%S%:z")
  end

  def jisx0301
    y = year
    era, base = if @jd >= 2458605 then ["R", 2018]
                elsif @jd >= 2447535 then ["H", 1988]
                elsif @jd >= 2424875 then ["S", 1925]
                elsif @jd >= 2419614 then ["T", 1911]
                elsif @jd >= 2405160 then ["M", 1867]
                end
    era ? format("%s%02d.%02d.%02d", era, y - base, mon, mday) : to_s
  end

  def rfc2822
    strftime("%a, %-d %b %Y %T %z")
  end
  alias rfc822 rfc2822

  def httpdate
    new_offset(0).strftime("%a, %d %b %Y %T GMT")
  end

  def asctime
    strftime("%a %b %e %T %Y")
  end
  alias ctime asctime

  def strftime(format = "%F")
    Topaz::Strftime.format(self, format)
  end

  def to_date
    self.class == Date ? self : Date.__topaz_from_jd(@jd, @sg)
  end

  def to_datetime
    DateTime.new(year, mon, mday, 0, 0, 0, 0, @sg)
  end

  def to_time
    Time.local(year, mon, mday)
  end

  def new_offset(offset = 0)
    to_datetime.new_offset(offset)
  end

  def deconstruct_keys(keys)
    h = {year: year, month: mon, day: mday, yday: yday, wday: wday}
    keys ? h.slice(*keys) : h
  end

  def marshal_dump
    [0, @jd, 0, 0r, 0, @sg]
  end

  def marshal_load(array)
    _, jd, _, _, _, sg = array
    __topaz_init(jd, sg)
  end

  # Topaz's own, for Topaz::Strftime.

  def __topaz_nanoseconds
    0
  end

  def __topaz_utc_offset
    0
  end

  def __topaz_epoch_seconds
    (@jd - 2440588) * 86400
  end

  private

  def __topaz_init(jd, start, fraction = 0)
    @jd = jd
    @sg = start
    @civil = nil
    self
  end

  def __topaz_civil
    @civil ||= Calendar.jd_to_civil(@jd, @sg)
  end

  def __topaz_with_jd(jd, fraction = 0)
    self.class.__topaz_from_jd(jd, @sg)
  end
end

class DateTime < Date
  class << self
    def civil(y = -4712, m = 1, d = 1, h = 0, min = 0, s = 0, of = 0, start = Date::ITALY)
      jd = Date::Calendar.valid_civil(y, m, d, start)
      raise Date::Error, "invalid date" if jd.nil?
      h += 24 if h < 0
      min += 60 if min < 0
      s += 60 if s < 0
      raise Date::Error, "invalid date" if h < 0 || h > 24 || min < 0 || min > 59 || s < 0 || s >= 60
      if h == 24
        h = 0
        jd += 1
      end
      offset = __topaz_offset_seconds(of)
      local = h * 3600 + min * 60 + s
      __topaz_from_local(jd, local, offset, start)
    end
    alias new civil

    def jd(jd = 0, h = 0, min = 0, s = 0, of = 0, start = Date::ITALY)
      __topaz_from_local(jd, h * 3600 + min * 60 + s, __topaz_offset_seconds(of), start)
    end

    def ordinal(y = -4712, yday = 1, h = 0, min = 0, s = 0, of = 0, start = Date::ITALY)
      jd = Date::Calendar.valid_ordinal(y, yday, start)
      raise Date::Error, "invalid date" if jd.nil?
      __topaz_from_local(jd, h * 3600 + min * 60 + s, __topaz_offset_seconds(of), start)
    end

    def commercial(y = -4712, w = 1, d = 1, h = 0, min = 0, s = 0, of = 0, start = Date::ITALY)
      jd = Date::Calendar.valid_commercial(y, w, d, start)
      raise Date::Error, "invalid date" if jd.nil?
      __topaz_from_local(jd, h * 3600 + min * 60 + s, __topaz_offset_seconds(of), start)
    end

    def now(start = Date::ITALY)
      Time.now.to_datetime(start)
    end

    def parse(string = "-4712-01-01T00:00:00+00:00", comp = true, start = Date::ITALY, limit: 128)
      __topaz_from_hash(Date._parse(string, comp), start)
    end

    def strptime(string = "-4712-01-01T00:00:00+00:00", format = "%FT%T%z", start = Date::ITALY)
      hash = Date._strptime(string, format)
      raise Date::Error, "invalid date" if hash.nil? || hash[:leftover]
      __topaz_from_hash(hash, start)
    end

    %w[iso8601 rfc3339 xmlschema rfc2822 rfc822 httpdate jisx0301].each do |name|
      define_method(name) do |string = "-4712-01-01T00:00:00+00:00", start = Date::ITALY, limit: 128|
        __topaz_from_hash(Topaz::DateParser.parse(string, true), start)
      end
    end

    def __topaz_from_hash(hash, start)
      raise Date::Error, "invalid date" if hash.nil? || hash.empty?
      if hash[:seconds]
        seconds = hash[:seconds]
        offset = hash[:offset] || 0
        whole = seconds.floor
        dt = __topaz_from_utc(2440588 + whole.div(86400), whole % 86400, seconds - whole, start)
        return dt.new_offset(Rational(offset, 86400))
      end
      date = Date.__topaz_from_hash(hash, start)
      fraction = hash[:sec_fraction] || 0
      offset = hash[:offset] || 0
      sec = hash[:sec] || 0
      sec = 59 if sec == 60
      civil(date.year, date.mon, date.mday, hash[:hour] || 0, hash[:min] || 0,
            sec + fraction, Rational(offset, 86400), start)
    end

    def __topaz_offset_seconds(of)
      case of
      when String
        m = of.match(/\A([-+])(\d{1,2}):?(\d{2})?\z/) or return 0
        s = m[2].to_i * 3600 + m[3].to_i * 60
        m[1] == "-" ? -s : s
      when Rational, Integer, Float
        (of * 86400).round
      else
        0
      end
    end

    def __topaz_from_local(jd, local_seconds, offset, start)
      whole = local_seconds.floor
      fraction = local_seconds - whole
      utc = whole - offset
      jd += utc.div(86400)
      __topaz_from_utc(jd, utc % 86400, fraction, start, offset)
    end

    def __topaz_from_utc(jd, df, sf, start, offset = 0)
      dt = allocate
      dt.__send__(:__topaz_init_time, jd, df, sf.to_r, offset, start)
      dt
    end
  end

  def hour
    __topaz_local[1].div(3600)
  end

  def minute
    __topaz_local[1] % 3600 / 60
  end
  alias min minute

  def second
    __topaz_local[1] % 60
  end
  alias sec second

  def second_fraction
    @sf
  end
  alias sec_fraction second_fraction

  def offset
    Rational(@of, 86400)
  end

  def zone
    sign = @of < 0 ? "-" : "+"
    a = @of.abs
    format("%s%02d:%02d", sign, a / 3600, a % 3600 / 60)
  end

  def day_fraction
    Rational(__topaz_local[1], 86400) + @sf / 86400
  end

  def ajd
    Rational(@jd * 2 - 1, 2) + Rational(@df, 86400) + @sf / 86400
  end

  def jd
    __topaz_local[0]
  end

  def new_offset(of = 0)
    offset = self.class.__topaz_offset_seconds(of)
    self.class.__topaz_from_utc(@jd, @df, @sf, @sg, offset)
  end

  def +(other)
    case other
    when Integer
      self.class.__topaz_from_utc(@jd + other, @df, @sf, @sg, @of)
    when Numeric
      total = Rational(@df, 1) + @sf + other.to_r * 86400
      whole = total.floor
      self.class.__topaz_from_utc(@jd + whole.div(86400), whole % 86400, total - whole, @sg, @of)
    else
      raise TypeError, "expected numeric"
    end
  end

  def >>(n)
    date = Date.new(year, mon, mday, @sg) >> n
    self.class.civil(date.year, date.mon, date.mday, hour, minute, second + @sf, offset, @sg)
  end

  def to_s
    strftime("%Y-%m-%dT%H:%M:%S%:z")
  end

  def inspect
    nanos = (@sf * 1_000_000_000).to_i
    "#<#{self.class}: #{to_s} ((#{@jd}j,#{@df}s,#{nanos}n),#{@of >= 0 ? "+" : "-"}#{@of.abs}s,#{@sg.is_a?(Float) ? @sg : "#{@sg}j"})>"
  end

  def iso8601(n = 0)
    n > 0 ? strftime("%Y-%m-%dT%H:%M:%S.%#{n}N%:z") : strftime("%Y-%m-%dT%H:%M:%S%:z")
  end
  alias xmlschema iso8601
  alias rfc3339 iso8601

  def jisx0301(n = 0)
    date = to_date.jisx0301
    date + (n > 0 ? strftime("T%H:%M:%S.%#{n}N%:z") : strftime("T%H:%M:%S%:z"))
  end

  def strftime(format = "%FT%T%:z")
    Topaz::Strftime.format(self, format)
  end

  def to_date
    Date.__topaz_from_jd(jd, @sg)
  end

  def to_datetime
    self
  end

  def to_time
    seconds = (@jd - 2440588) * 86400 + @df + @sf
    Time.at(seconds).getlocal(@of)
  end

  def deconstruct_keys(keys)
    h = {year: year, month: mon, day: mday, yday: yday, wday: wday, hour: hour,
         min: minute, sec: second, sec_fraction: @sf, zone: zone}
    keys ? h.slice(*keys) : h
  end

  def marshal_dump
    [0, @jd, @df, @sf, @of, @sg]
  end

  def marshal_load(array)
    _, jd, df, sf, of, sg = array
    __topaz_init_time(jd, df, sf, of, sg)
  end

  def __topaz_nanoseconds
    (@sf * 1_000_000_000).to_i
  end

  def __topaz_utc_offset
    @of
  end

  def __topaz_epoch_seconds
    (@jd - 2440588) * 86400 + @df + @sf
  end

  private

  def __topaz_init_time(jd, df, sf, of, sg)
    @jd = jd
    @df = df
    @sf = sf
    @of = of
    @sg = sg
    @civil = nil
    @local = nil
    self
  end

  # The local JD and seconds into the local day.
  def __topaz_local
    @local ||= begin
      local = @df + @of
      [@jd + local.div(86400), local % 86400]
    end
  end

  def __topaz_civil
    @civil ||= Calendar.jd_to_civil(__topaz_local[0], @sg)
  end
end

class Time
  def to_date
    Date.civil(year, month, day, Date::ITALY)
  end

  def to_datetime(start = Date::ITALY)
    DateTime.civil(year, month, day, hour, min, sec + Rational(nsec, 1_000_000_000),
                   Rational(utc_offset, 86400), start)
  end
end

module Topaz
  # Date._parse and Date._strptime.
  module DateParser
    MONTHS = {"jan" => 1, "feb" => 2, "mar" => 3, "apr" => 4, "may" => 5, "jun" => 6,
              "jul" => 7, "aug" => 8, "sep" => 9, "oct" => 10, "nov" => 11, "dec" => 12}
    DAYS = {"sun" => 0, "mon" => 1, "tue" => 2, "wed" => 3, "thu" => 4, "fri" => 5, "sat" => 6}
    ZONES = {"utc" => 0, "ut" => 0, "gmt" => 0, "z" => 0, "est" => -5 * 3600, "edt" => -4 * 3600,
             "cst" => -6 * 3600, "cdt" => -5 * 3600, "mst" => -7 * 3600, "mdt" => -6 * 3600,
             "pst" => -8 * 3600, "pdt" => -7 * 3600, "jst" => 9 * 3600, "cet" => 3600,
             "cest" => 7200, "bst" => 3600, "ist" => 5 * 3600 + 1800}

    module_function

    def zone_offset(zone)
      return nil if zone.nil?
      z = zone.strip.downcase
      return ZONES[z] if ZONES.key?(z)
      if (m = z.match(/\A(?:gmt|utc)?([-+])(\d{1,2})(?::?(\d{2}))?(?::?(\d{2}))?\z/))
        s = m[2].to_i * 3600 + m[3].to_i * 60 + m[4].to_i
        return m[1] == "-" ? -s : s
      end
      nil
    end

    def parse(string, comp = true)
      string = Topaz.convert_type(string, String, :to_str)
      h = {}
      str = string.dup
      # A time, possibly with fractions, a meridian and a zone.
      if (m = str.match(/(\d{1,2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?\s*([ap]\.?m\.?)?(?:\s*((?:gmt|utc)?[-+]\d{1,2}(?::?\d{2})?|z\b|[a-z]{3,4}\b(?!\s*\d{1,2}[,\s]))?)?/i))
        hour = m[1].to_i
        if m[5]
          hour %= 12
          hour += 12 if m[5].downcase.start_with?("p")
        end
        h[:hour] = hour
        h[:min] = m[2].to_i
        h[:sec] = m[3].to_i if m[3]
        h[:sec_fraction] = Rational(m[4].to_i, 10**m[4].size) if m[4]
        if m[6] && (offset = zone_offset(m[6]))
          h[:zone] = m[6]
          h[:offset] = offset
        end
        str = m.pre_match + " " + m.post_match
      elsif (m = str.match(/(\d{1,2})\s*([ap])\.?m\.?\b/i))
        h[:hour] = m[1].to_i % 12 + (m[2].downcase == "p" ? 12 : 0)
        str = m.pre_match + " " + m.post_match
      end
      if (m = str.match(/\b(sun|mon|tue|wed|thu|fri|sat)[a-z]*\.?\b/i))
        h[:wday] = DAYS[m[1].downcase]
        str = m.pre_match + " " + m.post_match
      end
      if (m = str.match(/([-+]?\d{2,})-(\d{1,2})-(\d{1,2})/))
        # ISO 8601: 2024-01-31
        h[:year] = m[1].to_i
        h[:mon] = m[2].to_i
        h[:mday] = m[3].to_i
      elsif (m = str.match(/\b(\d{4})(\d{2})(\d{2})(?:t(\d{2})(\d{2})(\d{2})?)?\b/i))
        h[:year] = m[1].to_i
        h[:mon] = m[2].to_i
        h[:mday] = m[3].to_i
        if m[4]
          h[:hour] = m[4].to_i
          h[:min] = m[5].to_i
          h[:sec] = m[6].to_i if m[6]
        end
      elsif (m = str.match(/(\d{1,2})(?:st|nd|rd|th)?\.?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:,?\s*(-?\d+))?/i))
        # 31 January 2024
        h[:mday] = m[1].to_i
        h[:mon] = MONTHS[m[2].downcase]
        h[:year] = __topaz_year(m[3], comp) if m[3]
      elsif (m = str.match(/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(?:(\d{1,2})(?:st|nd|rd|th)?)?(?:,?\s*(-?\d{3,}|'\d{2}|\d{2}\b(?!:)))?/i))
        # January 31, 2024
        h[:mon] = MONTHS[m[1].downcase]
        h[:mday] = m[2].to_i if m[2]
        h[:year] = __topaz_year(m[3].delete("'"), comp) if m[3]
      elsif (m = str.match(%r{(\d{1,4})/(\d{1,2})(?:/(-?\d+))?}))
        # 2024/01/31 or 01/31/2024 (US)
        if m[1].size > 2
          h[:year] = m[1].to_i
          h[:mon] = m[2].to_i
          h[:mday] = m[3].to_i if m[3]
        else
          h[:mon] = m[1].to_i
          h[:mday] = m[2].to_i
          h[:year] = __topaz_year(m[3], comp) if m[3]
        end
      elsif (m = str.match(/(\d{1,2})\.(\d{1,2})\.(-?\d+)/))
        # 31.01.2024
        h[:mday] = m[1].to_i
        h[:mon] = m[2].to_i
        h[:year] = __topaz_year(m[3], comp)
      elsif (m = str.match(/\b(\d{4})-(\d{3})\b/))
        h[:year] = m[1].to_i
        h[:yday] = m[2].to_i
      elsif (m = str.match(/\b(\d{4})\b/)) && h.empty?
        h[:year] = m[1].to_i
      end
      if !h.key?(:offset) && (m = str.match(/(?:\s|\A)([-+]\d{2}:?\d{2}|z|utc|gmt)\s*\z/i))
        h[:zone] = m[1]
        h[:offset] = zone_offset(m[1])
      end
      h
    end

    def __topaz_year(text, comp)
      y = text.to_i
      if comp && text.size == 2 && !text.start_with?("-")
        y += y >= 69 ? 1900 : 2000
      end
      y
    end

    # Date._strptime: the fields of string as format describes it, or nil.
    def strptime(string, format)
      string = string.to_s
      h = {}
      pos = scan(string, 0, format.to_s, h)
      return nil if pos.nil?
      if h.key?(:_merid)
        merid = h.delete(:_merid)
        h[:hour] = (h[:hour] || 0) % 12 + merid
      end
      if (cent = h.delete(:_cent))
        h[:year] = cent * 100 + (h[:year] ? h[:year] % 100 : 0)
      end
      h[:leftover] = string[pos..] if pos < string.size
      h
    end

    FIELDS = {
      "Y" => [/\A[-+]?\d+/, :year], "C" => [/\A[-+]?\d{1,2}/, :_cent],
      "m" => [/\A\d{1,2}/, :mon], "d" => [/\A ?\d{1,2}/, :mday], "e" => [/\A ?\d{1,2}/, :mday],
      "j" => [/\A\d{1,3}/, :yday], "H" => [/\A ?\d{1,2}/, :hour], "k" => [/\A ?\d{1,2}/, :hour],
      "I" => [/\A ?\d{1,2}/, :hour], "l" => [/\A ?\d{1,2}/, :hour], "M" => [/\A\d{1,2}/, :min],
      "S" => [/\A\d{1,2}/, :sec], "u" => [/\A\d/, :cwday], "w" => [/\A\d/, :wday],
      "G" => [/\A[-+]?\d+/, :cwyear], "V" => [/\A\d{1,2}/, :cweek], "s" => [/\A-?\d+/, :seconds],
    }
    COMPOSITES = {"F" => "%Y-%m-%d", "T" => "%H:%M:%S", "X" => "%H:%M:%S", "R" => "%H:%M",
                  "D" => "%m/%d/%y", "x" => "%m/%d/%y", "r" => "%I:%M:%S %p",
                  "c" => "%a %b %e %H:%M:%S %Y", "v" => "%e-%b-%Y", "+" => "%a %b %e %H:%M:%S %Z %Y"}

    # Matches format against string from pos, filling h; the position after
    # the match, or nil.
    def scan(string, pos, format, h)
      i = 0
      while i < format.size
        c = format[i]
        if c == "%" && i + 1 < format.size
          i += 1
          d = format[i]
          while "-_0^#".include?(d) && i + 1 < format.size
            i += 1
            d = format[i]
          end
          while d =~ /\d/ && i + 1 < format.size
            i += 1
            d = format[i]
          end
          while d == ":" && i + 1 < format.size
            i += 1
            d = format[i]
          end
          rest = string[pos..] || ""
          if (field = FIELDS[d])
            m = rest.match(field[0]) or return nil
            h[field[1]] = m[0].to_i
            pos += m[0].size
          elsif (composite = COMPOSITES[d])
            pos = scan(string, pos, composite, h) or return nil
          else
            case d
            when "y"
              m = rest.match(/\A\d{1,2}/) or return nil
              y = m[0].to_i
              h[:year] = y + (y >= 69 ? 1900 : 2000)
            when "L", "N"
              m = rest.match(/\A\d+/) or return nil
              h[:sec_fraction] = Rational(m[0].to_i, 10**m[0].size)
            when "p", "P"
              m = rest.match(/\A([ap])\.?m\.?/i) or return nil
              h[:_merid] = m[1].downcase == "p" ? 12 : 0
            when "b", "B", "h"
              m = rest.match(/\A(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*/i) or return nil
              h[:mon] = MONTHS[m[1].downcase]
            when "a", "A"
              m = rest.match(/\A(sun|mon|tue|wed|thu|fri|sat)[a-z]*/i) or return nil
              h[:wday] = DAYS[m[1].downcase]
            when "z", "Z"
              m = rest.match(/\A(?:(?:gmt|utc)?[-+]\d{1,2}(?::?\d{2}(?::?\d{2})?)?|z\b|[a-z]{3,4}\b)/i) or return nil
              h[:zone] = m[0]
              h[:offset] = zone_offset(m[0])
            when "Q"
              m = rest.match(/\A-?\d+/) or return nil
              h[:seconds] = Rational(m[0].to_i, 1000)
            when "n", "t"
              m = rest.match(/\A\s+/) or return nil
            when "%"
              return nil unless rest.start_with?("%")
              pos += 1
              i += 1
              next
            else
              return nil
            end
            pos += m[0].size
          end
          i += 1
        elsif c =~ /\s/
          pos += 1 while pos < string.size && string[pos] =~ /\s/
          i += 1
        else
          return nil unless string[pos] == c
          pos += 1
          i += 1
        end
      end
      pos
    end
  end
end
