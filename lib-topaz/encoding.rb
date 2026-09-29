# Encodings. Topaz strings are byte strings; each one carries an encoding
# tag (UTF-8 unless set with force_encoding, b or encode), and the methods
# here interpret the bytes accordingly.

class EncodingError < StandardError
end

class Encoding
  class CompatibilityError < EncodingError
  end

  class UndefinedConversionError < EncodingError
  end

  class InvalidByteSequenceError < EncodingError
  end

  class ConverterNotFoundError < EncodingError
  end

  @list = []

  def self.__topaz_define(name, aliases = [], ascii_compatible = true, dummy = false)
    enc = allocate
    enc.__send__(:__topaz_init, name, [name] + aliases, ascii_compatible, dummy)
    @list << enc
    ([name] + aliases).each do |n|
      const = n.tr("-", "_")
      [const, const.upcase].each do |c|
        const_set(c, enc) if c =~ /\A[A-Z][A-Za-z0-9_]*\z/ && !const_defined?(c, false)
      end
    end
    enc
  end

  def self.list
    @list.dup
  end

  def self.name_list
    @list.flat_map(&:names)
  end

  def self.aliases
    result = {}
    @list.each { |enc| enc.names.drop(1).each { |n| result[n] = enc.name } }
    result
  end

  def self.find(name)
    return name if name.is_a?(Encoding)
    name = Topaz.convert_type(name, String, :to_str)
    key = name.downcase
    if key == "external" || key == "locale" || key == "filesystem"
      return default_external
    end
    return default_internal if key == "internal"
    @list.each do |enc|
      enc.names.each { |n| return enc if n.downcase == key }
    end
    raise ArgumentError, "unknown encoding name - #{name}"
  end

  def self.default_external
    @default_external || UTF_8
  end

  def self.default_external=(enc)
    raise ArgumentError, "default external can not be nil" if enc.nil?
    @default_external = find(enc)
  end

  def self.default_internal
    @default_internal
  end

  def self.default_internal=(enc)
    @default_internal = enc.nil? ? nil : find(enc)
  end

  def self.locale_charmap
    "UTF-8"
  end

  def self.compatible?(a, b)
    ea = a.is_a?(Encoding) ? a : a.encoding
    eb = b.is_a?(Encoding) ? b : b.encoding
    return ea if ea.equal?(eb)
    if a.is_a?(String) && b.is_a?(String)
      return ea if b.empty?
      return eb if a.empty?
    end
    return nil unless ea.ascii_compatible? && eb.ascii_compatible?
    return ea if b.is_a?(String) && b.ascii_only?
    return eb if a.is_a?(String) && a.ascii_only?
    nil
  end

  def name
    @name
  end
  alias to_s name

  def names
    @names.dup
  end

  def ascii_compatible?
    @ascii_compatible
  end

  def dummy?
    @dummy
  end

  def unicode?
    @name.start_with?("UTF-")
  end

  def inspect
    return "#<Encoding:BINARY (ASCII-8BIT)>" if equal?(Encoding::BINARY)
    "#<Encoding:#{@name}#{" (dummy)" if @dummy}>"
  end

  def _dump(limit = -1)
    @name
  end

  def self._load(name)
    find(name)
  end

  private

  def __topaz_init(name, names, ascii_compatible, dummy)
    @name = name.freeze
    @names = names
    @ascii_compatible = ascii_compatible
    @dummy = dummy
  end
end

class Encoding
  __topaz_define("ASCII-8BIT", ["BINARY"])
  __topaz_define("UTF-8", ["CP65001"])
  __topaz_define("US-ASCII", ["ASCII", "ANSI_X3.4-1968", "646"])
  __topaz_define("ISO-8859-1", ["ISO8859-1"])
  __topaz_define("UTF-16BE", ["UCS-2BE"], false)
  __topaz_define("UTF-16LE", [], false)
  __topaz_define("UTF-32BE", ["UCS-4BE"], false)
  __topaz_define("UTF-32LE", ["UCS-4LE"], false)
  __topaz_define("UTF-16", [], false, true)
  __topaz_define("UTF-32", [], false, true)
  __topaz_define("Windows-1252", ["CP1252"])
  __topaz_define("Shift_JIS")
  __topaz_define("EUC-JP", ["eucJP"])
  __topaz_define("Windows-31J", ["CP932", "csWindows31J", "SJIS", "PCK"])
  # The rest of CRuby's encodings, by name: strings in them are treated
  # as bytes.
  __topaz_define("UTF8-MAC", ["UTF-8-MAC", "UTF-8-HFS"])
  __topaz_define("Big5", [])
  __topaz_define("Big5-HKSCS", ["Big5-HKSCS:2008"])
  __topaz_define("Big5-UAO", [])
  __topaz_define("CESU-8", [])
  __topaz_define("CP949", [])
  __topaz_define("Emacs-Mule", [])
  __topaz_define("EUC-KR", ["eucKR"])
  __topaz_define("EUC-TW", ["eucTW"])
  __topaz_define("GB18030", [])
  __topaz_define("GBK", ["CP936"])
  __topaz_define("ISO-8859-2", ["ISO8859-2"])
  __topaz_define("ISO-8859-3", ["ISO8859-3"])
  __topaz_define("ISO-8859-4", ["ISO8859-4"])
  __topaz_define("ISO-8859-5", ["ISO8859-5"])
  __topaz_define("ISO-8859-6", ["ISO8859-6"])
  __topaz_define("ISO-8859-7", ["ISO8859-7"])
  __topaz_define("ISO-8859-8", ["ISO8859-8"])
  __topaz_define("ISO-8859-9", ["ISO8859-9"])
  __topaz_define("ISO-8859-10", ["ISO8859-10"])
  __topaz_define("ISO-8859-11", ["ISO8859-11"])
  __topaz_define("ISO-8859-13", ["ISO8859-13"])
  __topaz_define("ISO-8859-14", ["ISO8859-14"])
  __topaz_define("ISO-8859-15", ["ISO8859-15"])
  __topaz_define("ISO-8859-16", ["ISO8859-16"])
  __topaz_define("KOI8-R", ["CP878"])
  __topaz_define("KOI8-U", [])
  __topaz_define("Windows-1250", ["CP1250"])
  __topaz_define("Windows-1251", ["CP1251"])
  __topaz_define("Windows-1253", ["CP1253"])
  __topaz_define("Windows-1254", ["CP1254"])
  __topaz_define("Windows-1257", ["CP1257"])
  __topaz_define("IBM437", ["CP437"])
  __topaz_define("IBM720", ["CP720"])
  __topaz_define("IBM737", ["CP737"])
  __topaz_define("IBM775", ["CP775"])
  __topaz_define("CP850", ["IBM850"])
  __topaz_define("IBM852", [])
  __topaz_define("CP852", [])
  __topaz_define("IBM855", [])
  __topaz_define("CP855", [])
  __topaz_define("IBM857", ["CP857"])
  __topaz_define("IBM860", ["CP860"])
  __topaz_define("IBM861", ["CP861"])
  __topaz_define("IBM862", ["CP862"])
  __topaz_define("IBM863", ["CP863"])
  __topaz_define("IBM864", ["CP864"])
  __topaz_define("IBM865", ["CP865"])
  __topaz_define("IBM866", ["CP866"])
  __topaz_define("IBM869", ["CP869"])
  __topaz_define("Windows-1258", ["CP1258"])
  __topaz_define("GB1988", [])
  __topaz_define("macCentEuro", [])
  __topaz_define("macCroatian", [])
  __topaz_define("macCyrillic", [])
  __topaz_define("macGreek", [])
  __topaz_define("macIceland", [])
  __topaz_define("macRoman", [])
  __topaz_define("macRomania", [])
  __topaz_define("macThai", [])
  __topaz_define("macTurkish", [])
  __topaz_define("macUkraine", [])
  __topaz_define("CP950", [])
  __topaz_define("CP951", [])
  __topaz_define("IBM037", ["ebcdic-cp-us"], false, true)
  __topaz_define("stateless-ISO-2022-JP", [])
  __topaz_define("eucJP-ms", ["euc-jp-ms"])
  __topaz_define("CP51932", [])
  __topaz_define("EUC-JIS-2004", ["EUC-JISX0213"])
  __topaz_define("GB2312", ["EUC-CN", "eucCN"])
  __topaz_define("GB12345", [])
  __topaz_define("ISO-2022-JP", ["ISO2022-JP"], false, true)
  __topaz_define("ISO-2022-JP-2", ["ISO2022-JP2"], false, true)
  __topaz_define("CP50220", [], false, true)
  __topaz_define("CP50221", [], false, true)
  __topaz_define("Windows-1256", ["CP1256"])
  __topaz_define("Windows-1255", ["CP1255"])
  __topaz_define("TIS-620", [])
  __topaz_define("Windows-874", ["CP874"])
  __topaz_define("MacJapanese", ["MacJapan"])
  __topaz_define("UTF-7", ["CP65000"], false, true)
  __topaz_define("UTF8-DoCoMo", [])
  __topaz_define("SJIS-DoCoMo", [])
  __topaz_define("UTF8-KDDI", [])
  __topaz_define("SJIS-KDDI", [])
  __topaz_define("ISO-2022-JP-KDDI", [], false, true)
  __topaz_define("stateless-ISO-2022-JP-KDDI", [])
  __topaz_define("UTF8-SoftBank", [])
  __topaz_define("SJIS-SoftBank", [])
end

module Topaz
  module EncodingSupport
    # The length of the valid UTF-8 character at byte i of str, or 0.
    def self.utf8_char_length(str, i, n)
      b = str.getbyte(i)
      return 1 if b < 0x80
      return 0 if b < 0xc2 || b > 0xf4
      need = b < 0xe0 ? 1 : b < 0xf0 ? 2 : 3
      return 0 if i + need >= n
      c = str.getbyte(i + 1)
      ok = case b
           when 0xe0 then c >= 0xa0 && c <= 0xbf
           when 0xed then c >= 0x80 && c <= 0x9f
           when 0xf0 then c >= 0x90 && c <= 0xbf
           when 0xf4 then c >= 0x80 && c <= 0x8f
           else c & 0xc0 == 0x80
           end
      return 0 unless ok
      k = 2
      while k <= need
        return 0 unless str.getbyte(i + k) & 0xc0 == 0x80
        k += 1
      end
      need + 1
    end

    # How many bytes of an invalid sequence at byte i one replacement
    # character stands for: the lead byte and the continuation bytes that
    # could still have belonged to it.
    def self.invalid_length(str, i, n)
      b = str.getbyte(i)
      return 1 if b < 0xc2 || b > 0xf4
      need = b < 0xe0 ? 1 : b < 0xf0 ? 2 : 3
      k = 1
      while k <= need && i + k < n
        c = str.getbyte(i + k)
        if k == 1
          ok = case b
               when 0xe0 then c >= 0xa0 && c <= 0xbf
               when 0xed then c >= 0x80 && c <= 0x9f
               when 0xf0 then c >= 0x90 && c <= 0xbf
               when 0xf4 then c >= 0x80 && c <= 0x8f
               else c & 0xc0 == 0x80
               end
        else
          ok = c & 0xc0 == 0x80
        end
        break unless ok
        k += 1
      end
      k
    end

    def self.ascii_only?(str)
      str.each_byte { |b| return false if b >= 0x80 }
      true
    end

    def self.valid_utf8?(str)
      Topaz.valid_utf8?(str)
    end

    # Replaces invalid UTF-8 in str, yielding each invalid sequence.
    def self.scrub_utf8(str)
      out = ""
      i = 0
      n = str.bytesize
      start = 0
      while i < n
        if str.getbyte(i) < 0x80
          i += 1
          next
        end
        len = utf8_char_length(str, i, n)
        if len > 0
          i += len
          next
        end
        out << str.byteslice(start, i - start)
        bad = invalid_length(str, i, n)
        out << yield(str.byteslice(i, bad))
        i += bad
        start = i
      end
      out << str.byteslice(start, n - start)
      out
    end

    def self.codepoints_utf8(str)
      str.unpack("U*")
    end

    def self.replacement_for(dst)
      dst.unicode? ? "\u{FFFD}" : "?"
    end

    def self.transcode(str, src, dst, opts)
      invalid_replace = opts[:invalid] == :replace
      undef_replace = opts[:undef] == :replace
      replace = opts[:replace]
      fallback = opts[:fallback]
      result = str

      if src.equal?(Encoding::UTF_8) || src.equal?(Encoding::US_ASCII)
        if !valid_utf8?(result)
          raise InvalidByteSequenceError, "invalid byte sequence in #{src}" unless invalid_replace
          result = scrub_utf8(result) { replace || replacement_for(dst) }
        end
        codepoints = nil
      elsif src.equal?(Encoding::BINARY)
        unless dst.equal?(Encoding::BINARY) || ascii_only?(result)
          out = ""
          result.each_byte do |b|
            if b < 0x80
              out << b.chr
            elsif fallback
              out << fallback[b.chr].to_s
            elsif undef_replace
              out << (replace || replacement_for(dst))
            else
              raise Encoding::UndefinedConversionError, "\"\\x#{b.to_s(16).upcase}\" from ASCII-8BIT to #{dst}"
            end
          end
          result = out
        end
        return result
      elsif src.equal?(Encoding::ISO_8859_1) || src.equal?(Encoding::Windows_1252)
        codepoints = result.bytes
        result = codepoints.pack("U*")
      elsif src.equal?(Encoding::UTF_16LE) || src.equal?(Encoding::UTF_16BE)
        units = result.unpack(src.equal?(Encoding::UTF_16LE) ? "v*" : "n*")
        codepoints = []
        i = 0
        while i < units.size
          u = units[i]
          if u >= 0xd800 && u < 0xdc00 && i + 1 < units.size
            codepoints << (((u - 0xd800) << 10) | (units[i + 1] - 0xdc00)) + 0x10000
            i += 2
          else
            codepoints << u
            i += 1
          end
        end
        result = codepoints.pack("U*")
      else
        return result
      end

      # result is now valid UTF-8.
      if dst.equal?(Encoding::UTF_8) || dst.equal?(Encoding::BINARY) && ascii_only?(result)
        result
      elsif dst.equal?(Encoding::US_ASCII) || dst.equal?(Encoding::BINARY) ||
            dst.equal?(Encoding::ISO_8859_1) || dst.equal?(Encoding::Windows_1252)
        limit = dst.equal?(Encoding::ISO_8859_1) || dst.equal?(Encoding::Windows_1252) ? 0x100 : 0x80
        out = ""
        result.unpack("U*").each do |cp|
          if cp < limit
            out << cp.chr
          elsif fallback
            out << fallback[[cp].pack("U")].to_s
          elsif undef_replace
            out << (replace || "?")
          else
            raise Encoding::UndefinedConversionError,
                  "U+#{cp.to_s(16).upcase.rjust(4, "0")} from UTF-8 to #{dst}"
          end
        end
        out
      elsif dst.equal?(Encoding::UTF_16LE) || dst.equal?(Encoding::UTF_16BE)
        units = []
        result.unpack("U*").each do |cp|
          if cp >= 0x10000
            cp -= 0x10000
            units << (0xd800 | (cp >> 10)) << (0xdc00 | (cp & 0x3ff))
          else
            units << cp
          end
        end
        units.pack(dst.equal?(Encoding::UTF_16LE) ? "v*" : "n*")
      elsif dst.equal?(Encoding::UTF_32LE) || dst.equal?(Encoding::UTF_32BE)
        result.unpack("U*").pack(dst.equal?(Encoding::UTF_32LE) ? "V*" : "N*")
      else
        result
      end
    end
  end
end

class String
  def encoding
    @__topaz_encoding || Encoding::UTF_8
  end

  def force_encoding(enc)
    raise FrozenError, "can't modify frozen String: #{inspect}" if frozen?
    enc = Encoding.find(enc)
    @__topaz_encoding = enc.equal?(Encoding::UTF_8) ? nil : enc
    self
  end

  def b
    s = dup
    s.force_encoding(Encoding::BINARY)
  end

  # These keep the encoding tag, which lives in an instance variable the
  # RPython methods do not see.
  alias __topaz_times *
  def *(times)
    s = __topaz_times(times)
    s.force_encoding(@__topaz_encoding) if @__topaz_encoding
    s
  end

  alias __topaz_replace replace
  def replace(other)
    __topaz_replace(other)
    enc = other.instance_variable_get(:@__topaz_encoding) if other.is_a?(String)
    @__topaz_encoding = enc
    self
  end

  def ascii_only?
    Topaz::EncodingSupport.ascii_only?(self)
  end

  def valid_encoding?
    enc = encoding
    if enc.equal?(Encoding::UTF_8)
      Topaz::EncodingSupport.valid_utf8?(self)
    elsif enc.equal?(Encoding::US_ASCII)
      ascii_only?
    else
      true
    end
  end

  def scrub(replacement = nil, &block)
    enc = encoding
    unless enc.equal?(Encoding::UTF_8) || enc.equal?(Encoding::US_ASCII)
      return dup
    end
    return dup if valid_encoding?
    result = Topaz::EncodingSupport.scrub_utf8(self) do |bad|
      block ? block.call(bad) : (replacement || "\u{FFFD}")
    end
    result.force_encoding(enc)
  end

  def scrub!(replacement = nil, &block)
    replace(scrub(replacement, &block))
  end

  def encode(*args, **opts)
    dst = args[0] ? Encoding.find(args[0]) : (Encoding.default_internal || Encoding::UTF_8)
    src = args[1] ? Encoding.find(args[1]) : encoding
    result = if src.equal?(dst)
      if opts[:invalid] == :replace && !valid_encoding?
        scrub(opts[:replace])
      else
        dup
      end
    else
      Topaz::EncodingSupport.transcode(self, src, dst, opts)
    end
    result = result.dup if result.equal?(self)
    case opts[:xml]
    when :text
      result = result.gsub(/[&<>]/, "&" => "&amp;", "<" => "&lt;", ">" => "&gt;")
    when :attr
      result = "\"" + result.gsub(/[&<>"]/, "&" => "&amp;", "<" => "&lt;", ">" => "&gt;", "\"" => "&quot;") + "\""
    end
    if opts[:universal_newline]
      result = result.gsub(/\r\n?/, "\n")
    elsif opts[:crlf_newline]
      result = result.gsub(/\n/, "\r\n")
    end
    result.force_encoding(dst)
  end

  def encode!(*args, **opts)
    result = encode(*args, **opts)
    replace(result)
    force_encoding(result.encoding)
  end

  def unicode_normalize(form = :nfc)
    return dup if ascii_only?
    require "unicode_normalize/normalize"
    UnicodeNormalize.normalize(self, form)
  end

  def unicode_normalize!(form = :nfc)
    replace(unicode_normalize(form))
  end

  def unicode_normalized?(form = :nfc)
    return true if ascii_only?
    require "unicode_normalize/normalize"
    UnicodeNormalize.normalized?(self, form)
  end
end

class Symbol
  def encoding
    to_s.ascii_only? ? Encoding::US_ASCII : Encoding::UTF_8
  end
end

class Regexp
  def encoding
    source.ascii_only? ? Encoding::US_ASCII : Encoding::UTF_8
  end

  def fixed_encoding?
    !source.ascii_only?
  end
end
