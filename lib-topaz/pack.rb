# Array#pack and String#unpack.
#
# Floats are packed by the builtin packer (Array#__topaz_pack); everything
# else, and all of unpack, is here.
module Topaz
  module Pack
    INTEGER_DIRECTIVES = "CcSsLlQqJjIiNnVv"
    SIGNED_DIRECTIVES = "cslqji"
    FLOAT_DIRECTIVES = "DdFfEeGg"
    HEX_DIGITS = "0123456789abcdef"
    BASE64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    UU = "`!\"\#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_"

    BASE64_VALUES = ::Array.new(256, -1)
    i = 0
    while i < 64
      BASE64_VALUES[BASE64.getbyte(i)] = i
      i += 1
    end

    # Parses a template into [directive, count, modifiers] triples. count is
    # an Integer, :star, or nil when the template gives none.
    # Templates are nearly always literals, so the parsed triples are kept
    # per template string; callers only read them.
    PARSED = {}

    def self.parse(template)
      template = Topaz.convert_type(template, String, :to_str)
      parsed = PARSED[template]
      return parsed if parsed
      parsed = parse_uncached(template)
      PARSED[template.dup.freeze] = parsed if PARSED.size < 256
      parsed
    end

    def self.parse_uncached(template)
      directives = []
      i = 0
      size = template.bytesize
      while i < size
        c = template[i]
        i += 1
        if c == "#"
          i += 1 while i < size && template[i] != "\n"
          next
        end
        next if c == " " || c == "\t" || c == "\n" || c == "\r" || c == "\f" || c == "\v" || c == "\0"
        mods = ""
        while i < size && (template[i] == "_" || template[i] == "!" || template[i] == "<" || template[i] == ">")
          mods += template[i]
          i += 1
        end
        unless mods.empty?
          mods.each_char do |m|
            unless "sSiIlLqQjJ".include?(c)
              raise ArgumentError, "'#{m}' allowed only after types sSiIlLqQjJ"
            end
          end
          if mods.include?("<") && mods.include?(">")
            raise RangeError, "Can't use both '<' and '>'"
          end
        end
        count = nil
        if i < size && template[i] == "*"
          count = :star
          i += 1
        elsif i < size && template.getbyte(i) >= 48 && template.getbyte(i) <= 57
          count = 0
          while i < size && template.getbyte(i) >= 48 && template.getbyte(i) <= 57
            count = count * 10 + (template.getbyte(i) - 48)
            i += 1
          end
          raise RangeError, "pack length too big" if count >= 0x8000000000000000
        end
        directives << [c, count, mods]
      end
      directives
    end

    def self.integer_size(d, mods)
      native = mods.include?("_") || mods.include?("!")
      if native && !"SsIiLlQqJj".include?(d)
        raise ArgumentError, "'#{mods[0]}' allowed only after types sSiIlLqQjJ"
      end
      case d
      when "C", "c" then 1
      when "S", "s", "n", "v" then 2
      when "I", "i", "N", "V" then 4
      when "L", "l" then native ? 8 : 4
      else 8
      end
    end

    def self.big_endian?(d, mods)
      d == "N" || d == "n" || mods.include?(">")
    end

    def self.to_integer(value)
      return value if value.is_a?(Integer)
      return value.to_i if value.is_a?(Float)
      Topaz.convert_type(value, Integer, :to_int)
    end

    def self.to_str(value)
      Topaz.convert_type(value, String, :to_str)
    end

    def self.pack(items, template)
      out = ""
      idx = 0
      parse(template).each do |d, count, mods|
        if INTEGER_DIRECTIVES.include?(d)
          size = integer_size(d, mods)
          big = big_endian?(d, mods)
          n = count == :star ? items.size - idx : (count || 1)
          n.times do
            raise ArgumentError, "too few arguments" if idx >= items.size
            v = to_integer(items[idx]) & ((1 << (size * 8)) - 1)
            idx += 1
            bytes = ::Array.new(size) { |k| (v >> (8 * k)) & 0xff }
            bytes.reverse! if big
            bytes.each { |b| out << b.chr }
          end
        elsif FLOAT_DIRECTIVES.include?(d)
          n = count == :star ? items.size - idx : (count || 1)
          n.times do
            raise ArgumentError, "too few arguments" if idx >= items.size
            f = items[idx]
            idx += 1
            raise TypeError, "can't convert #{f.nil? ? "nil" : f.class} into Float" unless f.is_a?(Numeric)
            out << [f.to_f].__topaz_pack(d)
          end
        else
          case d
          when "U"
            n = count == :star ? items.size - idx : (count || 1)
            n.times do
              raise ArgumentError, "too few arguments" if idx >= items.size
              out << utf8_encode(to_integer(items[idx]))
              idx += 1
            end
          when "w"
            n = count == :star ? items.size - idx : (count || 1)
            n.times do
              raise ArgumentError, "too few arguments" if idx >= items.size
              v = to_integer(items[idx])
              idx += 1
              raise ArgumentError, "can't compress negative numbers" if v < 0
              bytes = [v & 0x7f]
              v >>= 7
              while v > 0
                bytes.unshift((v & 0x7f) | 0x80)
                v >>= 7
              end
              bytes.each { |b| out << b.chr }
            end
          when "A", "a", "Z"
            raise ArgumentError, "too few arguments" if idx >= items.size
            s = items[idx].nil? && d != "Z" ? "" : to_str(items[idx])
            idx += 1
            if count == :star
              out << s
              out << "\0" if d == "Z"
            else
              len = count || 1
              if s.bytesize >= len
                out << s.byteslice(0, len)
              else
                out << s
                out << (d == "A" ? " " : "\0") * (len - s.bytesize)
              end
            end
          when "B", "b"
            raise ArgumentError, "too few arguments" if idx >= items.size
            s = to_str(items[idx])
            idx += 1
            bits = count == :star ? s.bytesize : (count || 1)
            byte = 0
            i = 0
            while i < bits
              bit = i < s.bytesize ? s.getbyte(i) & 1 : 0
              if d == "B"
                byte |= bit << (7 - (i % 8))
              else
                byte |= bit << (i % 8)
              end
              if i % 8 == 7
                out << byte.chr
                byte = 0
              end
              i += 1
            end
            out << byte.chr if bits % 8 != 0
          when "H", "h"
            raise ArgumentError, "too few arguments" if idx >= items.size
            s = to_str(items[idx])
            idx += 1
            digits = count == :star ? s.bytesize : (count || 1)
            byte = 0
            i = 0
            while i < digits
              c = i < s.bytesize ? s.getbyte(i) : 48
              nibble = (c >= 65 && c <= 90) || (c >= 97 && c <= 122) ? ((c & 7) + 9) & 15 : c & 15
              if (d == "H") == (i.even?)
                byte |= nibble << 4
              else
                byte |= nibble
              end
              if i.odd?
                out << byte.chr
                byte = 0
              end
              i += 1
            end
            out << byte.chr if digits.odd?
          when "m", "u"
            raise ArgumentError, "too few arguments" if idx >= items.size
            s = to_str(items[idx])
            idx += 1
            if d == "m" && count == 0
              out << base64_encode(s, 0, s.bytesize)
            else
              len = count == :star || count.nil? ? 1 : count
              if len <= 2
                len = 45
              elsif len > 63 && d == "u"
                len = 63
              else
                len = len / 3 * 3
              end
              pos = 0
              while pos < s.bytesize
                todo = [len, s.bytesize - pos].min
                if d == "m"
                  out << base64_encode(s, pos, todo) << "\n"
                else
                  out << uu_encode(s, pos, todo)
                end
                pos += todo
              end
            end
          when "M"
            raise ArgumentError, "too few arguments" if idx >= items.size
            s = items[idx].to_s
            idx += 1
            out << qp_encode(s, count.is_a?(Integer) && count > 1 ? count : 72)
          when "P", "p"
            raise ArgumentError, "too few arguments" if idx >= items.size
            out << [items[idx]].__topaz_pack(d)
            idx += 1
          when "x"
            out << "\0" * (count == :star ? 0 : (count || 1))
          when "X"
            n = count == :star ? 0 : (count || 1)
            raise ArgumentError, "X outside of string" if n > out.bytesize
            out = out.byteslice(0, out.bytesize - n)
          when "@"
            pos = count == :star ? out.bytesize : (count || 1)
            if pos > out.bytesize
              out << "\0" * (pos - out.bytesize)
            else
              out = out.byteslice(0, pos)
            end
          else
            raise ArgumentError, "unknown pack directive '#{d}' in '#{template}'"
          end
        end
      end
      out
    end

    def self.utf8_encode(cp)
      raise RangeError, "pack(U): value out of range" if cp < 0 || cp > 0x7fffffff
      if cp < 0x80
        cp.chr
      elsif cp < 0x800
        (0xc0 | (cp >> 6)).chr + (0x80 | (cp & 0x3f)).chr
      elsif cp < 0x10000
        (0xe0 | (cp >> 12)).chr + (0x80 | ((cp >> 6) & 0x3f)).chr + (0x80 | (cp & 0x3f)).chr
      elsif cp < 0x200000
        (0xf0 | (cp >> 18)).chr + (0x80 | ((cp >> 12) & 0x3f)).chr +
          (0x80 | ((cp >> 6) & 0x3f)).chr + (0x80 | (cp & 0x3f)).chr
      else
        raise RangeError, "pack(U): value out of range"
      end
    end

    def self.base64_encode(s, pos, len)
      s.__topaz_base64_encode(pos, len)
    end

    def self.uu_encode(s, pos, len)
      out = UU[len]
      stop = pos + len
      while pos < stop
        b0 = s.getbyte(pos)
        b1 = pos + 1 < stop ? s.getbyte(pos + 1) : 0
        b2 = pos + 2 < stop ? s.getbyte(pos + 2) : 0
        out << UU[b0 >> 2] << UU[((b0 & 3) << 4) | (b1 >> 4)]
        out << UU[((b1 & 15) << 2) | (b2 >> 6)] << UU[b2 & 63]
        pos += 3
      end
      out << "\n"
    end

    def self.qp_encode(s, line_len)
      out = ""
      n = 0
      prev = nil
      s.each_byte do |c|
        if c > 126 || (c < 32 && c != 10 && c != 9) || c == 61
          out << "=" << HEX_DIGITS[c >> 4].upcase << HEX_DIGITS[c & 15].upcase
          n += 3
          prev = nil
        elsif c == 10
          out << "=\n" if prev == 32 || prev == 9
          out << "\n"
          n = 0
          prev = c
          next
        else
          out << c.chr
          n += 1
          prev = c
        end
        if n > line_len
          out << "=\n"
          n = 0
          prev = 10
        end
      end
      out << "=\n" if n > 0
      out
    end

    def self.unpack(str, template, offset, single)
      str = Topaz.convert_type(str, String, :to_str)
      len = str.bytesize
      raise ArgumentError, "offset can't be negative" if offset < 0
      raise ArgumentError, "offset outside of string" if offset > len
      result = []
      pos = offset
      parse(template).each do |d, count, mods|
        if INTEGER_DIRECTIVES.include?(d)
          size = integer_size(d, mods)
          big = big_endian?(d, mods)
          signed = SIGNED_DIRECTIVES.include?(d)
          n = count == :star ? (len - pos) / size : (count || 1)
          n.times do
            if pos + size > len
              result << nil
              next
            end
            v = str.__topaz_unpack_integer(pos, size, big, signed)
            pos += size
            result << v
          end
        elsif FLOAT_DIRECTIVES.include?(d)
          double = "DdEG".include?(d)
          size = double ? 8 : 4
          big = d == "G" || d == "g"
          n = count == :star ? (len - pos) / size : (count || 1)
          n.times do
            if pos + size > len
              result << nil
              next
            end
            bits = 0
            k = 0
            while k < size
              byte = str.getbyte(big ? pos + k : pos + size - 1 - k)
              bits = (bits << 8) | byte
              k += 1
            end
            pos += size
            result << (double ? bits_to_double(bits) : bits_to_single(bits))
          end
        else
          case d
          when "U"
            n = count == :star ? nil : (count || 1)
            while pos < len && (n.nil? || n > 0)
              cp, pos = utf8_decode(str, pos)
              result << cp
              n -= 1 if n
            end
          when "w"
            n = count == :star ? nil : (count || 1)
            while pos < len && (n.nil? || n > 0)
              v = 0
              loop do
                b = str.getbyte(pos)
                pos += 1
                v = (v << 7) | (b & 0x7f)
                break if b & 0x80 == 0 || pos >= len
              end
              result << v
              n -= 1 if n
            end
          when "A", "a", "Z"
            n = count == :star ? len - pos : [count || 1, len - pos].min
            s = str.byteslice(pos, n)
            if d == "Z"
              nul = s.index("\0")
              if nul
                s = s.byteslice(0, nul)
                n = nul + 1 if count == :star
              end
            elsif d == "A"
              stop = s.bytesize
              stop -= 1 while stop > 0 && (s.getbyte(stop - 1) == 32 || s.getbyte(stop - 1) == 0)
              s = s.byteslice(0, stop)
            end
            pos += n
            result << s
          when "B", "b"
            bits = count == :star ? (len - pos) * 8 : [count || 1, (len - pos) * 8].min
            s = ""
            i = 0
            while i < bits
              byte = str.getbyte(pos + i / 8)
              bit = d == "B" ? (byte >> (7 - (i % 8))) & 1 : (byte >> (i % 8)) & 1
              s << (bit == 1 ? "1" : "0")
              i += 1
            end
            pos += (bits + 7) / 8
            result << s
          when "H", "h"
            digits = count == :star ? (len - pos) * 2 : [count || 1, (len - pos) * 2].min
            s = str.__topaz_unpack_hex(pos, digits, d == "H")
            pos += (digits + 1) / 2
            result << s
          when "m"
            result << base64_decode(str.byteslice(pos, len - pos), count == 0)
            pos = len
          when "u"
            result << uu_decode(str.byteslice(pos, len - pos))
            pos = len
          when "M"
            result << qp_decode(str.byteslice(pos, len - pos))
            pos = len
          when "x"
            n = count == :star ? 0 : (count || 1)
            raise ArgumentError, "x outside of string" if pos + n > len
            pos += n
          when "X"
            n = count == :star ? 0 : (count || 1)
            raise ArgumentError, "X outside of string" if n > pos
            pos -= n
          when "@"
            n = count == :star ? 0 : (count || 1)
            raise ArgumentError, "@ outside of string" if offset + n > len
            pos = offset + n
          else
            raise ArgumentError, "unknown unpack directive '#{d}' in '#{template}'"
          end
        end
        return result[0] if single && !result.empty?
      end
      single ? nil : result
    end

    def self.utf8_decode(str, pos)
      b = str.getbyte(pos)
      if b < 0x80
        return [b, pos + 1]
      elsif b & 0xe0 == 0xc0
        n = 1
        cp = b & 0x1f
      elsif b & 0xf0 == 0xe0
        n = 2
        cp = b & 0x0f
      elsif b & 0xf8 == 0xf0
        n = 3
        cp = b & 0x07
      else
        raise ArgumentError, "malformed UTF-8 character"
      end
      if pos + n >= str.bytesize
        raise ArgumentError, "malformed UTF-8 character (expected #{n + 1} bytes, given #{str.bytesize - pos} bytes)"
      end
      k = 1
      while k <= n
        c = str.getbyte(pos + k)
        raise ArgumentError, "malformed UTF-8 character" if c.nil? || c & 0xc0 != 0x80
        cp = (cp << 6) | (c & 0x3f)
        k += 1
      end
      [cp, pos + n + 1]
    end

    def self.base64_decode(s, strict)
      out = ""
      if strict
        raise ArgumentError, "invalid base64" if s.bytesize % 4 != 0
        i = 0
        size = s.bytesize
        while i < size
          a = BASE64_VALUES[s.getbyte(i)]
          b = BASE64_VALUES[s.getbyte(i + 1)]
          c = s.getbyte(i + 2)
          e = s.getbyte(i + 3)
          raise ArgumentError, "invalid base64" if a < 0 || b < 0
          if c == 61
            raise ArgumentError, "invalid base64" if e != 61 || i + 4 != size || b & 15 != 0
            out << ((a << 2) | (b >> 4)).chr
          else
            c = BASE64_VALUES[c]
            raise ArgumentError, "invalid base64" if c < 0
            if e == 61
              raise ArgumentError, "invalid base64" if i + 4 != size || c & 3 != 0
              out << ((a << 2) | (b >> 4)).chr << (((b & 15) << 4) | (c >> 2)).chr
            else
              e = BASE64_VALUES[e]
              raise ArgumentError, "invalid base64" if e < 0
              out << ((a << 2) | (b >> 4)).chr << (((b & 15) << 4) | (c >> 2)).chr
              out << (((c & 3) << 6) | e).chr
            end
          end
          i += 4
        end
        return out
      end
      sextets = []
      s.each_byte do |byte|
        break if byte == 61
        v = BASE64_VALUES[byte]
        sextets << v if v >= 0
      end
      i = 0
      while i + 3 < sextets.size
        a, b, c, e = sextets[i], sextets[i + 1], sextets[i + 2], sextets[i + 3]
        out << ((a << 2) | (b >> 4)).chr << (((b & 15) << 4) | (c >> 2)).chr << (((c & 3) << 6) | e).chr
        i += 4
      end
      rest = sextets.size - i
      if rest >= 2
        a, b = sextets[i], sextets[i + 1]
        out << ((a << 2) | (b >> 4)).chr
        if rest == 3
          c = sextets[i + 2]
          out << (((b & 15) << 4) | (c >> 2)).chr
        end
      end
      out
    end

    def self.uu_decode(s)
      out = ""
      s.each_line do |line|
        line = line.chomp
        next if line.empty?
        n = (line.getbyte(0) - 32) & 63
        break if n == 0
        i = 1
        chunk = ""
        while chunk.bytesize < n && i < line.bytesize
          vals = (0..3).map { |k| c = line.getbyte(i + k); c.nil? ? 0 : (c - 32) & 63 }
          chunk << ((vals[0] << 2) | (vals[1] >> 4)).chr
          chunk << (((vals[1] & 15) << 4) | (vals[2] >> 2)).chr
          chunk << (((vals[2] & 3) << 6) | vals[3]).chr
          i += 4
        end
        out << chunk.byteslice(0, n)
      end
      out
    end

    def self.qp_decode(s)
      out = ""
      i = 0
      size = s.bytesize
      while i < size
        c = s.getbyte(i)
        if c == 61
          if i + 1 < size && s.getbyte(i + 1) == 10
            i += 2
            next
          elsif i + 2 < size && s.getbyte(i + 1) == 13 && s.getbyte(i + 2) == 10
            i += 3
            next
          end
          hex = s.byteslice(i + 1, 2)
          if hex && hex.bytesize == 2 && hex =~ /\A[0-9a-fA-F]{2}\z/
            out << hex.to_i(16).chr
            i += 3
            next
          end
        end
        out << c.chr
        i += 1
      end
      out
    end

    def self.bits_to_double(bits)
      sign = bits >> 63
      exp = (bits >> 52) & 0x7ff
      mant = bits & 0xfffffffffffff
      v = if exp == 0x7ff
        mant == 0 ? Float::INFINITY : Float::NAN
      elsif exp == 0
        Math.ldexp(mant.to_f, -1074)
      else
        Math.ldexp((mant | 0x10000000000000).to_f, exp - 1075)
      end
      sign == 1 ? -v : v
    end

    def self.bits_to_single(bits)
      sign = bits >> 31
      exp = (bits >> 23) & 0xff
      mant = bits & 0x7fffff
      v = if exp == 0xff
        mant == 0 ? Float::INFINITY : Float::NAN
      elsif exp == 0
        Math.ldexp(mant.to_f, -149)
      else
        Math.ldexp((mant | 0x800000).to_f, exp - 150)
      end
      sign == 1 ? -v : v
    end
  end
end

class Array
  alias __topaz_pack pack

  def pack(template, buffer: nil)
    out = Topaz::Pack.pack(self, template)
    return out unless buffer
    buffer << out
  end
end

class String
  # "U" and "U*" (htmlentities decodes every character with unpack("U"))
  # have an RPython decoder; the other templates go through Topaz::Pack.
  def unpack(template, offset: 0, &block)
    if offset == 0 && (template == "U" || template == "U*")
      result = __topaz_unpack_utf8(template.bytesize == 1 ? 1 : -1)
    else
      result = Topaz::Pack.unpack(self, template, offset, false)
    end
    return result unless block
    result.each(&block)
    nil
  end

  def unpack1(template, offset: 0)
    if offset == 0 && (template == "U" || template == "U*")
      return __topaz_unpack_utf8_one
    end
    Topaz::Pack.unpack(self, template, offset, true)
  end
end
