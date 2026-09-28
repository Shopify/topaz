# StringScanner (strscan.so) in Ruby. Positions are byte offsets, as in
# CRuby. Regexps are matched in place at the scan pointer with
# Regexp#__topaz_match_at; a pattern using \A, ^, \G or lookbehind is
# matched against the rest of the string instead, since there the string
# is taken to start at the pointer.
class StringScanner
  Version = "3.1.6"
  Id = "$Id$"

  class Error < StandardError; end
  ::ScanError = Error unless defined?(::ScanError)

  def self.must_C_version
    self
  end

  def initialize(string, _dup = false, fixed_anchor: false)
    @string = Topaz.convert_type(string, String, :to_str)
    @fixed_anchor = fixed_anchor ? true : false
    @pos = 0
    __topaz_clear_match
  end

  def initialize_copy(other)
    @string = other.string
    @fixed_anchor = other.fixed_anchor?
    @pos = other.pos
    @match = other.instance_variable_get(:@match)
    @match_start = other.instance_variable_get(:@match_start)
    @match_end = other.instance_variable_get(:@match_end)
    @last_pos = other.instance_variable_get(:@last_pos)
  end

  def fixed_anchor?
    @fixed_anchor
  end

  attr_reader :string

  def string=(string)
    @string = Topaz.convert_type(string, String, :to_str)
    reset
    string
  end

  def concat(string)
    @string << Topaz.convert_type(string, String, :to_str)
    self
  end
  alias << concat

  def pos
    @pos
  end
  alias pointer pos

  def pos=(pos)
    pos = Integer(pos)
    pos += @string.bytesize if pos < 0
    raise RangeError, "index out of range" if pos < 0 || pos > @string.bytesize
    @pos = pos
  end
  alias pointer= pos=

  def charpos
    @string.byteslice(0, @pos).length
  end

  def reset
    @pos = 0
    __topaz_clear_match
    self
  end

  def terminate
    @pos = @string.bytesize
    __topaz_clear_match
    self
  end
  alias clear terminate

  def eos?
    @pos >= @string.bytesize
  end

  def empty?
    warn "StringScanner#empty? is obsolete; use #eos? instead", uplevel: 1 if $VERBOSE
    eos?
  end

  def rest?
    !eos?
  end

  def rest
    @string.byteslice(@pos, @string.bytesize - @pos) || ""
  end

  def rest_size
    @string.bytesize - @pos
  end

  def restsize
    rest_size
  end

  def beginning_of_line?
    @pos == 0 || @string.getbyte(@pos - 1) == 10
  end
  alias bol? beginning_of_line?

  def scan(pattern)
    __topaz_scan(pattern, true, true, true)
  end

  def skip(pattern)
    __topaz_scan(pattern, true, false, true)
  end

  def match?(pattern)
    __topaz_scan(pattern, false, false, true)
  end

  def check(pattern)
    __topaz_scan(pattern, false, true, true)
  end

  def scan_full(pattern, advance, return_string)
    __topaz_scan(pattern, advance, return_string, true)
  end

  def scan_until(pattern)
    __topaz_scan(pattern, true, true, false)
  end

  def skip_until(pattern)
    __topaz_scan(pattern, true, false, false)
  end

  def exist?(pattern)
    __topaz_scan(pattern, false, false, false)
  end

  def check_until(pattern)
    __topaz_scan(pattern, false, true, false)
  end

  def search_full(pattern, advance, return_string)
    __topaz_scan(pattern, advance, return_string, false)
  end

  def getch
    return __topaz_clear_match && nil if eos?
    length = __topaz_char_length(@pos)
    __topaz_set_literal_match(@pos, @pos + length)
    @pos += length
    matched
  end

  def get_byte
    return __topaz_clear_match && nil if eos?
    __topaz_set_literal_match(@pos, @pos + 1)
    @pos += 1
    matched
  end
  alias getbyte get_byte

  def scan_byte
    return __topaz_clear_match && nil if eos?
    byte = @string.getbyte(@pos)
    __topaz_set_literal_match(@pos, @pos + 1)
    @pos += 1
    byte
  end

  def peek_byte
    @string.getbyte(@pos)
  end

  def peek(length)
    raise ArgumentError, "negative string size (or size too big)" if length < 0
    @string.byteslice(@pos, length) || ""
  end

  def peep(length)
    peek(length)
  end

  def scan_integer(base: 10)
    pattern = case base
              when 10 then /[+-]?\d+/
              when 16 then /[+-]?(?:0x)?[0-9a-fA-F]+/
              else raise ArgumentError, "Unsupported integer base: #{base.inspect}, expected 10 or 16"
              end
    string = scan(pattern)
    string && string.to_i(base)
  end

  def unscan
    raise Error, "unscan error: not scanned yet" unless @last_pos
    @pos = @last_pos
    __topaz_clear_match
    self
  end

  def matched?
    !@match_start.nil?
  end

  def matched
    return nil unless @match_start
    @string.byteslice(@match_start, @match_end - @match_start)
  end

  def matched_size
    return nil unless @match_start
    @match_end - @match_start
  end

  def pre_match
    return nil unless @match_start
    @string.byteslice(0, @match_start)
  end

  def post_match
    return nil unless @match_start
    @string.byteslice(@match_end, @string.bytesize - @match_end)
  end

  def [](index)
    return nil unless @match_start
    if @match.nil?
      raise IndexError, "undefined group name reference: #{index}" if index.is_a?(String) || index.is_a?(Symbol)
      return index == 0 || index == -1 ? matched : nil
    end
    if (index.is_a?(String) || index.is_a?(Symbol)) && !@match.names.include?(index.to_s)
      raise IndexError, "undefined group name reference: #{index}"
    end
    @match[index]
  end

  def size
    return nil unless @match_start
    @match ? @match.size : 1
  end

  def captures
    return nil unless @match_start
    @match ? @match.captures : []
  end

  def values_at(*indexes)
    return nil unless @match_start
    indexes.map { |i| self[i] }
  end

  def named_captures
    return {} unless @match
    @match.named_captures
  end

  def inspect
    return "#<#{self.class} fin>" if eos?
    if @pos == 0
      "#<#{self.class} #{@pos}/#{@string.bytesize} @ #{__topaz_inspect_after}>"
    else
      "#<#{self.class} #{@pos}/#{@string.bytesize} #{__topaz_inspect_before} @ #{__topaz_inspect_after}>"
    end
  end

  private

  def __topaz_clear_match
    @match = nil
    @match_start = nil
    @match_end = nil
    true
  end

  def __topaz_set_literal_match(start, stop)
    @last_pos = @pos
    @match = nil
    @match_start = start
    @match_end = stop
  end

  def __topaz_char_length(pos)
    byte = @string.getbyte(pos)
    return 1 unless @string.encoding == Encoding::UTF_8 && byte >= 0xc0
    length = byte >= 0xf0 ? 4 : byte >= 0xe0 ? 3 : 2
    [length, @string.bytesize - pos].min
  end

  # Whether a regexp has to see the rest of the string as a string of its
  # own.
  def __topaz_needs_rest?(regexp)
    source = regexp.source
    source.include?("\\A") || source.include?("^") || source.include?("\\G") ||
      source.include?("(?<=") || source.include?("(?<!")
  end

  def __topaz_scan(pattern, advance, return_string, anchored)
    if pattern.is_a?(String)
      match_start = match_end = nil
      if anchored
        if @string.byteslice(@pos, pattern.bytesize) == pattern
          match_start = @pos
          match_end = @pos + pattern.bytesize
        end
      else
        index = @string.byteindex(pattern, @pos)
        if index
          match_start = index
          match_end = index + pattern.bytesize
        end
      end
      unless match_start
        __topaz_clear_match
        return nil
      end
      match = nil
    else
      raise TypeError, "wrong argument type #{pattern.class} (expected Regexp)" unless pattern.is_a?(Regexp)
      if !@fixed_anchor && @pos > 0 && __topaz_needs_rest?(pattern)
        rest = self.rest
        match = pattern.__topaz_match_at(rest, 0, anchored)
        base = @pos
      else
        match = pattern.__topaz_match_at(@string, @pos, anchored)
        base = 0
      end
      unless match
        __topaz_clear_match
        return nil
      end
      match_start, match_end = match.byteoffset(0)
      match_start += base
      match_end += base
    end
    @last_pos = @pos
    @match = match
    @match_start = match_start
    @match_end = match_end
    length = match_end - @pos
    @pos = match_end if advance
    if return_string
      @string.byteslice(@last_pos, length)
    else
      length
    end
  end

  def __topaz_inspect_before
    start = @pos > 5 ? @pos - 5 : 0
    text = @string.byteslice(start, @pos - start)
    "\"" + (start > 0 ? "..." : "") + text.inspect[1..-2] + "\""
  end

  def __topaz_inspect_after
    text = @string.byteslice(@pos, 5)
    "\"" + text.inspect[1..-2] + (@string.bytesize - @pos > 5 ? "..." : "") + "\""
  end
end
