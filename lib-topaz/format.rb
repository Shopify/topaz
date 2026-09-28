# Kernel#format / sprintf and String#%.
module Topaz
  module Format
    DIGITS = "0123456789abcdef"

    module_function

    def format(fmt, args)
      fmt = Topaz.convert_type(fmt, String, :to_str)
      out = +""
      argi = 0
      hash = nil
      i = 0
      n = fmt.bytesize
      while i < n
        c = fmt.getbyte(i)
        if c != 37 # %
          j = fmt.index("%", i) || n
          out << fmt.byteslice(i, j - i)
          i = j
          next
        end
        i += 1
        if i >= n
          raise ArgumentError, "incomplete format specifier; use %% (double %) instead"
        end
        flags = ""
        width = nil
        precision = nil
        name = nil
        value = nil
        have_value = false
        loop do
          ch = fmt[i]
          case ch
          when " ", "#", "+", "-", "0"
            flags << ch
            i += 1
          when "<", "{"
            close = fmt.index(ch == "<" ? ">" : "}", i)
            raise ArgumentError, "malformed name - unmatched parenthesis" unless close
            name = fmt[i + 1...close]
            hash ||= __topaz_hash_arg(args)
            key = name.to_sym
            value = hash.fetch(key) do
              hash.default_proc ? hash.default_proc.call(hash, key) : (hash.key?(key) ? hash[key] : raise(KeyError, "key<#{name}> not found"))
            end
            have_value = true
            i = close + 1
            if ch == "{"
              out << __topaz_pad(value.to_s, flags, width)
              name = :done
              break
            end
          when "*"
            i += 1
            w = Topaz.convert_type(args.fetch(argi) { raise ArgumentError, "too few arguments" }, Integer, :to_int)
            argi += 1
            if w < 0
              flags << "-"
              w = -w
            end
            width = w
          when "1", "2", "3", "4", "5", "6", "7", "8", "9"
            j = i
            j += 1 while j < n && fmt.getbyte(j) >= 48 && fmt.getbyte(j) <= 57
            number = fmt[i...j].to_i
            if fmt[j] == "$"
              value = args.fetch(number - 1) { raise ArgumentError, "too few arguments" }
              have_value = true
              i = j + 1
            else
              width = number
              i = j
            end
          when "."
            i += 1
            if fmt[i] == "*"
              precision = Topaz.convert_type(args.fetch(argi) { raise ArgumentError, "too few arguments" }, Integer, :to_int)
              argi += 1
              i += 1
            else
              j = i
              j += 1 while j < n && fmt.getbyte(j) >= 48 && fmt.getbyte(j) <= 57
              precision = fmt[i...j].to_i
              i = j
            end
          else
            break
          end
          raise ArgumentError, "malformed format string - %#{fmt[i - 1]}" if i >= n
        end
        next if name == :done
        type = fmt[i]
        i += 1
        if type == "%"
          out << "%"
          next
        end
        if type.nil? || type == "\n" || type == "\0"
          out << "%" << (type || "")
          next
        end
        unless have_value
          raise ArgumentError, "too few arguments" if argi >= args.size
          value = args[argi]
          argi += 1
        end
        out << __topaz_directive(type, value, flags, width, precision)
      end
      out
    end

    def __topaz_hash_arg(args)
      if args.size != 1 || !args[0].is_a?(Hash)
        raise ArgumentError, "one hash required"
      end
      args[0]
    end

    def __topaz_pad(str, flags, width, zero_ok = false)
      return str if width.nil? || str.size >= width
      if flags.include?("-")
        str + " " * (width - str.size)
      elsif zero_ok && flags.include?("0")
        sign = str[0] == "-" || str[0] == "+" || str[0] == " " ? str[0] : ""
        body = str[sign.size..]
        prefix = ""
        if body =~ /\A0[xXbBo]/
          prefix = body[0, 2]
          body = body[2..]
        end
        sign + prefix + "0" * (width - str.size) + body
      else
        " " * (width - str.size) + str
      end
    end

    def __topaz_integer(value)
      case value
      when Integer then value
      when Float
        raise FloatDomainError, value.to_s if value.nan? || value.infinite?
        value.floor == value ? value.to_i : value.floor
      when String then Integer(value)
      when nil then raise TypeError, "can't convert nil into Integer"
      else Topaz.convert_type(value, Integer, :to_int)
      end
    end

    def __topaz_directive(type, value, flags, width, precision)
      case type
      when "d", "i", "u"
        v = __topaz_integer(value)
        digits = v.abs.to_s
        digits = digits.rjust(precision, "0") if precision
        sign = v < 0 ? "-" : (flags.include?("+") ? "+" : (flags.include?(" ") ? " " : ""))
        __topaz_pad(sign + digits, flags, width, precision.nil?)
      when "x", "X", "o", "b", "B"
        v = __topaz_integer(value)
        base = type == "o" ? 8 : (type == "b" || type == "B" ? 2 : 16)
        explicit_sign = flags.include?("+") || flags.include?(" ")
        if v < 0 && !explicit_sign
          digits = __topaz_twos_complement(v, base)
          digits = ".." + digits unless precision || flags.include?("0")
        else
          digits = v.abs.to_s(base)
        end
        digits = digits.upcase if type == "X"
        digits = digits.rjust(precision, v < 0 && !explicit_sign ? DIGITS[base - 1] : "0") if precision
        prefix = ""
        if flags.include?("#")
          prefix = case type
                   when "x" then "0x"
                   when "X" then "0X"
                   when "b" then "0b"
                   when "B" then "0B"
                   when "o" then digits.start_with?("0") ? "" : "0"
                   end
          prefix = "" if v == 0 && type != "o"
        end
        sign = v < 0 && explicit_sign ? "-" : (explicit_sign && v >= 0 ? (flags.include?("+") ? "+" : " ") : "")
        __topaz_pad(sign + prefix + digits, flags, width, precision.nil?)
      when "f", "e", "E", "g", "G", "a", "A"
        __topaz_float(type, value, flags, width, precision)
      when "c"
        s = value.is_a?(Integer) ? [value].pack("U") : value.to_s[0].to_s
        __topaz_pad(s, flags, width)
      when "s"
        s = value.to_s
        s = s[0, precision] if precision
        __topaz_pad(s, flags, width)
      when "p"
        s = value.inspect
        s = s[0, precision] if precision
        __topaz_pad(s, flags, width)
      else
        raise ArgumentError, "malformed format string - %#{type}"
      end
    end

    def __topaz_twos_complement(v, base)
      k = 1
      k += 1 while base**k < -v * base
      digits = (base**k + v).to_s(base)
      max = DIGITS[base - 1]
      digits = digits.rjust(k, max)
      digits = digits.sub(/\A#{max}+/, "")
      max + digits
    end

    def __topaz_float(type, value, flags, width, precision)
      v = case value
          when Float then value
          when Integer, Rational then value.to_f
          when String then Float(value)
          when nil then raise TypeError, "can't convert nil into Float"
          else Topaz.convert_type(value, Float, :to_f)
          end
      if v.nan? || v.infinite?
        body = v.nan? ? "NaN" : "Inf"
        sign = v.infinite? && v < 0 ? "-" : (flags.include?("+") ? "+" : (flags.include?(" ") ? " " : ""))
        return __topaz_pad(sign + body, flags.delete("0"), width)
      end
      precision ||= 6
      negative = v < 0 || (v == 0.0 && 1.0 / v < 0)
      a = v.abs
      alt = flags.include?("#")
      body = case type
             when "f"
               __topaz_fixed(a, precision, alt)
             when "e", "E"
               s = __topaz_exponent(a, precision, alt)
               type == "E" ? s.upcase : s
             when "g", "G"
               s = __topaz_general(a, precision == 0 ? 1 : precision, alt)
               type == "G" ? s.upcase : s
             else
               s = __topaz_hexfloat(a, precision)
               type == "A" ? s.upcase.sub("0X", "0X") : s
             end
      sign = negative ? "-" : (flags.include?("+") ? "+" : (flags.include?(" ") ? " " : ""))
      __topaz_pad(sign + body, flags, width, true)
    end

    # CRuby rounds a float to the shortest decimal digits that read back
    # as it, rounding half to even there; beyond those digits it prints the
    # exact binary value.

    # [digits, decpt] of a nonnegative finite float: a = 0.DIGITS * 10**decpt.
    def __topaz_shortest(a)
      return ["0", 1] if a == 0.0
      r = a.__topaz_formatd("r", 0, false)
      exp = 0
      if (e = r.index("e"))
        exp = r[e + 1..].to_i
        r = r[0, e]
      end
      intpart, frac = r.split(".")
      frac ||= ""
      digits = intpart + frac
      decpt = intpart.size + exp
      while digits.size > 1 && digits.start_with?("0")
        digits = digits[1..]
        decpt -= 1
      end
      digits = digits.sub(/0+\z/, "")
      digits = "0" if digits.empty?
      [digits, decpt]
    end

    # Rounds digits to keep of them, half to even; [digits, decpt].
    def __topaz_round_digits(digits, decpt, keep)
      return ["0", decpt] if keep < 0
      return [digits, decpt] if keep >= digits.size
      kept = digits[0, keep]
      nextd = digits[keep]
      rest = digits[keep + 1..] || ""
      up = nextd > "5" || (nextd == "5" && (rest =~ /[1-9]/ || (kept.empty? ? false : kept[-1].to_i.odd?)))
      if up
        if kept.empty?
          return ["1", decpt + 1]
        end
        n = (kept.to_i + 1).to_s
        if n.size > kept.size
          return [n, decpt + 1]
        end
        kept = n.rjust(keep, "0")
      end
      kept = "0" if kept.empty?
      [kept, decpt]
    end

    def __topaz_fixed(a, precision, alt)
      digits, decpt = __topaz_shortest(a)
      # With no digit to keep, the exact value decides, as in C.
      if precision >= digits.size - decpt || decpt + precision <= 0
        return a.__topaz_formatd("f", precision, alt)
      end
      digits, decpt = __topaz_round_digits(digits, decpt, decpt + precision)
      digits = digits.ljust(decpt + precision, "0") if decpt + precision > digits.size
      if decpt <= 0
        int = "0"
        frac = ("0" * -decpt + digits)[0, precision].ljust(precision, "0")
      else
        int = digits[0, decpt].ljust(decpt, "0")
        frac = (digits[decpt..] || "").ljust(precision, "0")[0, precision]
      end
      precision == 0 ? (alt ? int + "." : int) : "#{int}.#{frac}"
    end

    def __topaz_exponent(a, precision, alt)
      digits, decpt = __topaz_shortest(a)
      if precision + 1 >= digits.size
        return a.__topaz_formatd("e", precision, alt)
      end
      digits, decpt = __topaz_round_digits(digits, decpt, precision + 1)
      digits = digits.ljust(precision + 1, "0")
      e = a == 0.0 ? 0 : decpt - 1
      mant = precision == 0 ? (alt ? digits[0] + "." : digits[0]) : "#{digits[0]}.#{digits[1..]}"
      "#{mant}e#{e < 0 ? "-" : "+"}#{e.abs.to_s.rjust(2, "0")}"
    end

    def __topaz_general(a, precision, alt)
      digits, decpt = __topaz_shortest(a)
      rd, rdecpt = __topaz_round_digits(digits, decpt, precision)
      x = a == 0.0 ? 0 : rdecpt - 1
      s = if x < -4 || x >= precision
            __topaz_exponent(a, precision - 1, alt)
          else
            __topaz_fixed(a, precision - 1 - x, alt)
          end
      unless alt
        if s.include?("e")
          m, e = s.split("e")
          m = m.sub(/\.?0+\z/, "") if m.include?(".")
          s = "#{m}e#{e}"
        elsif s.include?(".")
          s = s.sub(/\.?0+\z/, "")
        end
      end
      s
    end

    def __topaz_hexfloat(a, precision)
      return "0x0p+0" if a == 0.0
      m, e = Math.frexp(a)
      m *= 2
      e -= 1
      hex = +""
      frac = m - 1
      13.times do
        frac *= 16
        d = frac.to_i
        hex << DIGITS[d]
        frac -= d
      end
      hex = hex.sub(/0+\z/, "")
      "0x1#{hex.empty? ? "" : "." + hex}p#{e >= 0 ? "+" : "-"}#{e.abs}"
    end
  end
end

class String
  def %(args)
    Topaz::Format.format(self, args.is_a?(Array) ? args : [args])
  end
end

module Kernel
  def sprintf(format, *args)
    Topaz::Format.format(format, args)
  end
  alias format sprintf
  private :sprintf, :format
end
