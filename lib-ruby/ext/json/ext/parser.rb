# The C half of json's parser (json/ext/parser.so) in Ruby:
# JSON::Ext::ParserConfig, which json/ext.rb wraps as JSON::Ext::Parser.
#
# A recursive-descent parser over byte offsets. Strings, numbers and
# whitespace runs are matched in place with Regexp#__topaz_match_at.
module JSON
  module Ext
    class ParserConfig
      STRING_RUN = /[^"\\\x00-\x1f]*/n
      NUMBER = /-?(?:0|[1-9][0-9]*)(\.[0-9]+)?([eE][-+]?[0-9]+)?/n
      NUMBER_START = /-?[0-9.eE+\-]*/n
      SPACES = /[ \t\r\n]*/n
      ESCAPES = {
        0x22 => "\"", 0x5c => "\\", 0x2f => "/", 0x62 => "\b",
        0x66 => "\f", 0x6e => "\n", 0x72 => "\r", 0x74 => "\t",
      }.freeze

      def initialize(opts = nil)
        opts ||= {}
        opts = Topaz.convert_type(opts, Hash, :to_hash) unless opts.is_a?(Hash)
        @max_nesting = 100
        if opts.key?(:max_nesting)
          depth = opts[:max_nesting]
          @max_nesting = depth ? Integer(depth) : 0
        end
        @allow_nan = !!opts[:allow_nan]
        @allow_trailing_comma = !!opts[:allow_trailing_comma]
        @symbolize_names = !!opts[:symbolize_names]
        @freeze = !!opts[:freeze]
        @on_load = opts[:on_load]
        @decimal_class = opts[:decimal_class]
        @duplicate_key = if !opts.key?(:allow_duplicate_key)
                           :warn
                         elsif opts[:allow_duplicate_key]
                           :ignore
                         else
                           :raise
                         end
      end

      def parse(source)
        source = Topaz.convert_type(source, String, :to_str)
        if source.encoding == Encoding::ASCII_8BIT
          source = source.dup.force_encoding(Encoding::UTF_8)
        elsif source.encoding != Encoding::UTF_8
          source = source.encode(Encoding::UTF_8)
        end
        @src = source
        @pos = 0
        @depth = 0
        value = __parse_value
        __skip_space
        __error("unexpected token at end of stream %s") if @pos < @src.bytesize
        value
      ensure
        @src = nil
      end

      private

      def __push(value)
        value = value.freeze if @freeze && !value.frozen?
        @on_load ? @on_load.call(value) : value
      end

      def __skip_space
        while true
          match = SPACES.__topaz_match_at(@src, @pos, true)
          @pos = match.byteoffset(0)[1]
          return unless @src.getbyte(@pos) == 0x2f # /
          case @src.getbyte(@pos + 1)
          when 0x2f
            stop = @src.byteindex("\n", @pos)
            @pos = stop ? stop + 1 : @src.bytesize
          when 0x2a
            stop = @src.byteindex("*/", @pos + 2)
            unless stop
              @pos = @src.bytesize
              __error("unexpected end of input, expected closing '*/'")
            end
            @pos = stop + 2
          else
            __error("unexpected token %s")
          end
        end
      end

      def __literal(word)
        @src.byteslice(@pos, word.bytesize) == word
      end

      def __parse_value
        __skip_space
        __error("unexpected end of input") if @pos >= @src.bytesize
        case @src.getbyte(@pos)
        when 0x22 # "
          __push(__parse_string(false))
        when 0x7b # {
          __parse_object
        when 0x5b # [
          __parse_array
        when 0x6e # n
          __error("unexpected token %s") unless __literal("null")
          @pos += 4
          __push(nil)
        when 0x74 # t
          __error("unexpected token %s") unless __literal("true")
          @pos += 4
          __push(true)
        when 0x66 # f
          __error("unexpected token %s") unless __literal("false")
          @pos += 5
          __push(false)
        when 0x4e # N
          __error("unexpected token %s") unless @allow_nan && __literal("NaN")
          @pos += 3
          __push(Float::NAN)
        when 0x49 # I
          __error("unexpected token %s") unless @allow_nan && __literal("Infinity")
          @pos += 8
          __push(Float::INFINITY)
        when 0x2d # -
          if __literal("-Infinity")
            __error("unexpected token %s") unless @allow_nan
            @pos += 9
            return __push(-Float::INFINITY)
          end
          __push(__parse_number)
        when 0x30..0x39
          __push(__parse_number)
        else
          __error("unexpected character: %s")
        end
      end

      def __parse_number
        start = @pos
        match = NUMBER.__topaz_match_at(@src, @pos, true)
        stop = match ? match.byteoffset(0)[1] : start
        text = @src.byteslice(start, stop - start)
        following = @src.getbyte(stop)
        if match.nil? || text == "-" || (following && following >= 0x30 && following <= 0x39)
          # "-", "01", "-01": reported from the start of the number.
          @pos = start
          __error("invalid number: %s")
        elsif following == 0x2e || following == 0x65 || following == 0x45
          # "1." and "1e": reported after the dot or exponent.
          @pos = stop + 1
          @pos += 1 if following != 0x2e && (@src.getbyte(@pos) == 0x2b || @src.getbyte(@pos) == 0x2d)
          __error("invalid number: %s")
        end
        @pos = stop
        if match[1] || match[2]
          if @decimal_class
            __decimal(text)
          else
            Float(text)
          end
        else
          text.to_i
        end
      end

      def __decimal(text)
        if defined?(::BigDecimal) && @decimal_class == ::BigDecimal
          BigDecimal(text)
        elsif @decimal_class == ::Float
          Float(text)
        elsif @decimal_class.respond_to?(:try_convert)
          @decimal_class.try_convert(text)
        elsif @decimal_class.is_a?(::Class) && Kernel.respond_to?(@decimal_class.name, true)
          Kernel.__send__(@decimal_class.name, text)
        else
          @decimal_class.new(text)
        end
      end

      def __parse_string(name)
        start = @pos
        @pos += 1
        buffer = nil
        while true
          run = STRING_RUN.__topaz_match_at(@src, @pos, true)
          run_end = run.byteoffset(0)[1]
          if buffer
            buffer << @src.byteslice(@pos, run_end - @pos)
          elsif @src.getbyte(run_end) == 0x22
            string = @src.byteslice(@pos, run_end - @pos)
            @pos = run_end + 1
            return __finish_string(string, name)
          else
            buffer = @src.byteslice(@pos, run_end - @pos)
          end
          @pos = run_end
          byte = @src.getbyte(@pos)
          if byte.nil?
            @pos = @src.bytesize
            __error("unexpected end of input, expected closing \"")
          elsif byte == 0x22
            @pos += 1
            return __finish_string(buffer, name)
          elsif byte == 0x5c
            __parse_escape(buffer)
          else
            __error("invalid ASCII control character in string: %s", raw: true)
          end
        end
      end

      def __parse_escape(buffer)
        code = @src.getbyte(@pos + 1)
        if (replacement = ESCAPES[code])
          buffer << replacement
          @pos += 2
        elsif code == 0x75 # u
          point = __hex4(@pos + 2)
          @pos += 6
          if point >= 0xd800 && point <= 0xdbff && __literal("\\u")
            low = __hex4(@pos + 2)
            if low >= 0xdc00 && low <= 0xdfff
              @pos += 6
              point = 0x10000 + ((point - 0xd800) << 10) + (low - 0xdc00)
            end
          end
          # A lone surrogate cannot be encoded; CRuby's parser also writes
          # it out as bytes.
          if point >= 0xd800 && point <= 0xdfff
            buffer << [0xef, 0xbf, 0xbd].pack("C*").force_encoding(Encoding::UTF_8)
          else
            buffer << [point].pack("U")
          end
        elsif code.nil?
          @pos = @src.bytesize
          __error("unexpected end of input, expected closing \"")
        else
          # Other escaped characters stand for themselves.
          length = __char_length(@pos + 1)
          buffer << @src.byteslice(@pos + 1, length)
          @pos += 1 + length
        end
      end

      def __char_length(at)
        byte = @src.getbyte(at)
        byte >= 0xf0 ? 4 : byte >= 0xe0 ? 3 : byte >= 0xc0 ? 2 : 1
      end

      def __hex4(at)
        digits = @src.byteslice(at, 4)
        unless digits && digits.bytesize == 4 && digits.match?(/\A\h{4}\z/)
          __error("incomplete unicode character escape sequence at %s")
        end
        digits.to_i(16)
      end

      def __finish_string(string, name)
        string.force_encoding(Encoding::UTF_8)
        if name
          return string.to_sym if @symbolize_names
          -string
        elsif @freeze
          -string
        else
          string
        end
      end

      def __enter
        @depth += 1
        if @max_nesting > 0 && @depth > @max_nesting
          raise JSON::NestingError, "nesting of #{@depth} is too deep"
        end
      end

      def __parse_array
        __enter
        @pos += 1
        array = []
        __skip_space
        if @src.getbyte(@pos) == 0x5d # ]
          @pos += 1
        else
          while true
            array << __parse_value
            __skip_space
            byte = @src.getbyte(@pos)
            if byte == 0x2c # ,
              @pos += 1
              if @allow_trailing_comma
                __skip_space
                if @src.getbyte(@pos) == 0x5d
                  @pos += 1
                  break
                end
              end
            elsif byte == 0x5d
              @pos += 1
              break
            elsif byte.nil?
              __error("unexpected end of input")
            else
              __error("expected ',' or ']' after array value")
            end
          end
        end
        @depth -= 1
        __push(array)
      end

      def __parse_object
        __enter
        @pos += 1
        object = {}
        __skip_space
        if @src.getbyte(@pos) == 0x7d # }
          @pos += 1
        else
          first = true
          while true
            __skip_space
            unless @src.getbyte(@pos) == 0x22
              if !first && @allow_trailing_comma && @src.getbyte(@pos) == 0x7d
                @pos += 1
                break
              end
              __error(first ? "expected object key, got %s" : "expected object key, got: %s")
            end
            key_pos = @pos
            key = __parse_string(true)
            __skip_space
            __error("expected ':' after object key") unless @src.getbyte(@pos) == 0x3a
            @pos += 1
            value = __parse_value
            if @duplicate_key != :ignore && object.key?(key)
              __duplicate_key(key, key_pos)
            end
            object[key] = value
            first = false
            __skip_space
            byte = @src.getbyte(@pos)
            if byte == 0x2c
              @pos += 1
            elsif byte == 0x7d
              @pos += 1
              break
            elsif byte.nil?
              __error("unexpected end of input")
            else
              __error("expected ',' or '}' after object value, got: %s")
            end
          end
        end
        @depth -= 1
        __push(object)
      end

      def __duplicate_key(key, key_pos)
        line, column = __position(key_pos)
        if @duplicate_key == :raise
          @pos = key_pos
          __error("duplicate key #{key.inspect.gsub("%", "%%")}")
        elsif JSON.respond_to?(:deprecation_warning)
          JSON.deprecation_warning(
            "detected duplicate key #{key.inspect} in JSON object. This will raise an error " \
            "in json 3.0 unless enabled via `allow_duplicate_key: true` " \
            "at line #{line} column #{column}")
        end
      end

      def __position(pos)
        before = @src.byteslice(0, pos)
        newline = before.rindex("\n")
        # As json 2.13 counts them: the line is one less after a newline.
        newlines = before.count("\n")
        line = newlines > 0 ? newlines : 1
        column = newline ? pos - newline : pos + 1
        [line, column]
      end

      # Raises a ParserError, showing up to 32 bytes from the error up to
      # the next whitespace ("EOF" at the end) in place of %s.
      def __error(format, raw: false)
        line, column = __position(@pos)
        fragment = "EOF"
        if @pos < @src.bytesize
          rest = @src.byteslice(@pos, 32).b
          length = rest.index(/[\0\n\t\r ]/n) || rest.bytesize
          if length > 0
            text = rest.byteslice(0, length)
            # Do not cut a character in two.
            length -= 1 while length > 0 && (text.getbyte(length - 1) & 0xc0) == 0x80 &&
                              !text.byteslice(0, length).dup.force_encoding(Encoding::UTF_8).valid_encoding?
            text = text.byteslice(0, length)
            fragment = "'#{text.force_encoding(Encoding::UTF_8)}'"
          elsif raw
            fragment = rest.force_encoding(Encoding::UTF_8)
          end
        end
        message = format.include?("%s") ? format.sub("%s") { fragment } : format
        error = JSON::ParserError.new("#{message} at line #{line} column #{column}")
        error.instance_variable_set(:@line, line)
        error.instance_variable_set(:@column, column)
        raise error
      end
    end
  end
end
