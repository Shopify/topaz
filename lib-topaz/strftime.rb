# strftime for Time, Date and DateTime. The object provides year, mon,
# mday, hour, min, sec, wday, yday, cwyear, cweek, cwday, zone and the
# topaz hooks __topaz_nanoseconds, __topaz_utc_offset and
# __topaz_epoch_seconds.
module Topaz
  module Strftime
    MONTHNAMES = [nil, "January", "February", "March", "April", "May", "June", "July",
                  "August", "September", "October", "November", "December"].freeze
    DAYNAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                "Saturday"].freeze

    module_function

    def format(t, fmt)
      fmt = Topaz.convert_type(fmt, String, :to_str)
      out = +""
      i = 0
      n = fmt.size
      while i < n
        c = fmt[i]
        if c != "%" || i + 1 >= n
          out << c
          i += 1
          next
        end
        j = i + 1
        flags = ""
        while j < n && "-_0^#".include?(fmt[j])
          flags << fmt[j]
          j += 1
        end
        width = nil
        while j < n && fmt.getbyte(j) >= 48 && fmt.getbyte(j) <= 57
          width = (width || 0) * 10 + (fmt.getbyte(j) - 48)
          j += 1
        end
        colons = 0
        while j < n && fmt[j] == ":"
          colons += 1
          j += 1
        end
        j += 1 if j < n && (fmt[j] == "E" || fmt[j] == "O") && j + 1 < n
        conv = j < n ? fmt[j] : nil
        piece = conv && directive(t, conv, flags, width, colons)
        if piece.nil?
          out << fmt[i..(j < n ? j : n - 1)]
        else
          out << piece
        end
        i = j + 1
      end
      out
    end

    def pad(str, flags, width, padding)
      return str if flags.include?("-")
      padding = " " if flags.include?("_")
      padding = "0" if flags.include?("0")
      return str if width.nil? || str.size >= width
      if padding == "0" && str.start_with?("-", "+")
        str[0] + "0" * (width - str.size) + str[1..]
      else
        padding * (width - str.size) + str
      end
    end

    def num(value, flags, width, default_width, padding = "0")
      pad(value.to_s, flags, width || default_width, padding)
    end

    def text(str, flags, width)
      str = str.upcase if flags.include?("^")
      str = str.swapcase if flags.include?("#")
      pad(str, flags, width, " ")
    end

    def fraction(t, digits)
      nanos = t.__topaz_nanoseconds
      if digits <= 9
        (nanos / 10**(9 - digits)).to_s.rjust(digits, "0")
      else
        nanos.to_s.rjust(9, "0") + "0" * (digits - 9)
      end
    end

    def offset(t, flags, width, colons)
      off = t.__topaz_utc_offset.to_i
      sign = off < 0 ? "-" : "+"
      off = off.abs
      hh = off / 3600
      mm = off % 3600 / 60
      ss = off % 60
      body = case colons
             when 0 then Topaz::Format.format("%02d%02d", [hh, mm])
             when 1 then Topaz::Format.format("%02d:%02d", [hh, mm])
             else Topaz::Format.format("%02d:%02d:%02d", [hh, mm, ss])
             end
      str = sign + body
      if width && width > str.size
        padding = flags.include?("_") ? " " : "0"
        if padding == "0"
          str = sign + "0" * (width - str.size) + body
        else
          str = " " * (width - str.size) + str
        end
      end
      str
    end

    def directive(t, c, flags, width, colons)
      case c
      when "Y"
        y = t.year
        y < 0 ? pad("-" + y.abs.to_s.rjust(4, "0"), flags, width, "0") : num(y, flags, width, 4)
      when "C" then num(t.year.div(100), flags, width, 2)
      when "y" then num(t.year % 100, flags, width, 2)
      when "m" then num(t.mon, flags, width, 2)
      when "B" then text(MONTHNAMES[t.mon], flags, width)
      when "b", "h" then text(MONTHNAMES[t.mon][0, 3], flags, width)
      when "d" then num(t.mday, flags, width, 2)
      when "e" then num(t.mday, flags, width, 2, " ")
      when "j" then num(t.yday, flags, width, 3)
      when "H" then num(t.hour, flags, width, 2)
      when "k" then num(t.hour, flags, width, 2, " ")
      when "I" then num((t.hour % 12).zero? ? 12 : t.hour % 12, flags, width, 2)
      when "l" then num((t.hour % 12).zero? ? 12 : t.hour % 12, flags, width, 2, " ")
      when "P"
        s = t.hour < 12 ? "am" : "pm"
        s = s.upcase if flags.include?("^")
        pad(s, flags, width, " ")
      when "p"
        s = t.hour < 12 ? "AM" : "PM"
        s = s.downcase if flags.include?("#")
        pad(s, flags, width, " ")
      when "M" then num(t.min, flags, width, 2)
      when "S" then num(t.sec, flags, width, 2)
      when "L" then fraction(t, width || 3)
      when "N" then fraction(t, width || 9)
      when "z" then offset(t, flags, width, colons)
      when "Z" then text(t.zone.to_s, flags, width)
      when "A" then text(DAYNAMES[t.wday], flags, width)
      when "a" then text(DAYNAMES[t.wday][0, 3], flags, width)
      when "u" then num(t.wday == 0 ? 7 : t.wday, flags, width, 1)
      when "w" then num(t.wday, flags, width, 1)
      when "G"
        y = t.cwyear
        num(y, flags, width, y < 0 ? 5 : 4)
      when "g" then num(t.cwyear % 100, flags, width, 2)
      when "V" then num(t.cweek, flags, width, 2)
      when "U" then num((t.yday + 6 - t.wday) / 7, flags, width, 2)
      when "W" then num((t.yday + 6 - (t.wday + 6) % 7) / 7, flags, width, 2)
      when "s" then num(t.__topaz_epoch_seconds.floor, flags, width, 1)
      when "Q" then num((t.__topaz_epoch_seconds * 1000).floor, flags, width, 1)
      when "n" then "\n"
      when "t" then "\t"
      when "%" then "%"
      when "c" then pad(format(t, "%a %b %e %H:%M:%S %Y"), flags, width, " ")
      when "D", "x" then pad(format(t, "%m/%d/%y"), flags, width, " ")
      when "F" then pad(format(t, "%Y-%m-%d"), flags, width, " ")
      when "v" then pad(format(t, "%e-%^b-%Y"), flags, width, " ")
      when "X", "T" then pad(format(t, "%H:%M:%S"), flags, width, " ")
      when "r" then pad(format(t, "%I:%M:%S %p"), flags, width, " ")
      when "R" then pad(format(t, "%H:%M"), flags, width, " ")
      when "+" then pad(format(t, "%a %b %e %H:%M:%S %Z %Y"), flags, width, " ")
      end
    end
  end
end
