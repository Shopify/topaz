# Marshal, format 4.8, in Ruby.
module Marshal
  MAJOR_VERSION = 4 unless const_defined?(:MAJOR_VERSION)
  MINOR_VERSION = 8 unless const_defined?(:MINOR_VERSION)

  # Integers from -2**30 to 2**30 - 1 are written as Fixnums.
  FIXNUM_MIN = -(2**30)
  FIXNUM_MAX = 2**30 - 1

  class Dumper
    def initialize(limit)
      @limit = limit
      @out = "".b
      @symbols = {}
      @objects = {}.compare_by_identity
    end

    attr_reader :out

    def byte(b)
      @out << (b & 0xff).chr
    end

    def long(n)
      if n == 0
        byte(0)
      elsif n > 0 && n < 123
        byte(n + 5)
      elsif n < 0 && n > -124
        byte(n - 5)
      else
        bytes = []
        x = n
        4.times do
          bytes << (x & 0xff)
          x >>= 8
          break if (n >= 0 && x == 0) || (n < 0 && x == -1)
        end
        byte(n >= 0 ? bytes.size : -bytes.size)
        bytes.each { |b| byte(b) }
      end
    end

    def bytes(string)
      string = string.b
      long(string.bytesize)
      @out << string
    end

    def symbol(sym)
      if (index = @symbols[sym])
        byte(0x3b) # ;
        long(index)
        return
      end
      @symbols[sym] = @symbols.size
      name = sym.to_s
      if name.ascii_only?
        byte(0x3a) # :
        bytes(name)
      else
        byte(0x49) # I
        byte(0x3a)
        bytes(name)
        long(1)
        symbol(:E)
        dump(true)
      end
    end

    # Encoding ivars for a string: [] for binary.
    def encoding_ivars(string)
      encoding = string.encoding
      if encoding == Encoding::ASCII_8BIT
        []
      elsif encoding == Encoding::UTF_8
        [[:E, true]]
      elsif encoding == Encoding::US_ASCII
        [[:E, false]]
      else
        [[:encoding, encoding.name]]
      end
    end

    def ivars_of(obj)
      obj.instance_variables.map { |name| [name, obj.instance_variable_get(name)] }
    end

    def write_ivars(ivars)
      long(ivars.size)
      ivars.each do |name, value|
        symbol(name.to_sym)
        dump(value)
      end
    end

    # The shortest digits, laid out as CRuby's Marshal does: 1.5, 1e2,
    # 1e-5, 12345678.9.
    def float_text(float)
      text = float.abs.to_s
      if text.include?("e")
        mantissa, exponent = text.split("e")
        int, frac = mantissa.split(".")
        digits = (int + frac.to_s).sub(/0+\z/, "")
        decpt = int.size + exponent.to_i
      else
        int, frac = text.split(".")
        frac = frac.to_s
        if int == "0"
          zeros = frac[/\A0*/].size
          digits = frac[zeros..].sub(/0+\z/, "")
          decpt = -zeros
        else
          digits = (int + frac).sub(/0+\z/, "")
          decpt = int.size
        end
      end
      sign = float < 0 ? "-" : ""
      count = digits.size
      if decpt < -3 || decpt > count
        "#{sign}#{digits[0]}#{count > 1 ? "." + digits[1..] : ""}e#{decpt - 1}"
      elsif decpt > 0
        rest = digits[decpt..].to_s
        "#{sign}#{digits[0, decpt]}#{rest.empty? ? "" : "." + rest}"
      else
        "#{sign}0.#{"0" * -decpt}#{digits}"
      end
    end

    def remember(obj)
      @objects[obj] = @objects.size
    end

    def class_name(klass)
      name = klass.name
      raise TypeError, "can't dump anonymous class #{klass}" if name.nil?
      name
    end

    def user_class(obj, base)
      klass = obj.class
      return if klass == base
      byte(0x43) # C
      symbol(class_name(klass).to_sym)
    end

    def extended(obj)
      singleton = obj.singleton_class rescue nil
      return unless singleton
      (singleton.ancestors - obj.class.ancestors).each do |mod|
        next if mod == singleton || !mod.instance_of?(Module)
        byte(0x65) # e
        symbol(class_name(mod).to_sym)
      end
    end

    def dump(obj, depth = 0)
      raise ArgumentError, "exceed depth limit" if @limit >= 0 && depth > @limit
      case obj
      when nil then return byte(0x30)
      when true then return byte(0x54)
      when false then return byte(0x46)
      when Integer
        if obj >= FIXNUM_MIN && obj <= FIXNUM_MAX
          byte(0x69) # i
          return long(obj)
        end
      when Symbol
        return symbol(obj)
      end

      if (index = @objects[obj])
        byte(0x40) # @
        return long(index)
      end

      if obj.respond_to?(:marshal_dump, true) && !obj.is_a?(Class) && !obj.is_a?(Module)
        remember(obj)
        data = obj.__send__(:marshal_dump)
        byte(0x55) # U
        symbol(class_name(obj.class).to_sym)
        return dump(data, depth + 1)
      end
      if obj.respond_to?(:_dump, true) && !obj.is_a?(Class) && !obj.is_a?(Module)
        data = obj.__send__(:_dump, @limit)
        raise TypeError, "_dump() must return string" unless data.is_a?(String)
        ivars = encoding_ivars(data) + ivars_of(data)
        byte(0x49) unless ivars.empty?
        byte(0x75) # u
        symbol(class_name(obj.class).to_sym)
        bytes(data)
        write_ivars(ivars) unless ivars.empty?
        remember(obj)
        return
      end

      remember(obj)
      case obj
      when Integer
        byte(0x6c) # l
        byte(obj < 0 ? 0x2d : 0x2b)
        magnitude = obj.abs
        digits = []
        while magnitude > 0
          digits << (magnitude & 0xff)
          magnitude >>= 8
        end
        digits << 0 if digits.size.odd?
        long(digits.size / 2)
        digits.each { |b| byte(b) }
      when Float
        byte(0x66) # f
        text = if obj.nan? then "nan"
               elsif obj.infinite? then obj > 0 ? "inf" : "-inf"
               elsif obj == 0.0 then (1.0 / obj) < 0 ? "-0" : "0"
               else
                 float_text(obj)
               end
        bytes(text)
      when String
        ivars = encoding_ivars(obj) + ivars_of(obj)
        byte(0x49) unless ivars.empty?
        extended(obj)
        user_class(obj, String)
        byte(0x22) # "
        bytes(obj)
        write_ivars(ivars) unless ivars.empty?
      when Regexp
        source = obj.source
        ivars = encoding_ivars(source)
        byte(0x49) unless ivars.empty?
        user_class(obj, Regexp)
        byte(0x2f) # /
        bytes(source)
        byte(obj.options)
        write_ivars(ivars) unless ivars.empty?
      when Array
        ivars = ivars_of(obj)
        byte(0x49) unless ivars.empty?
        extended(obj)
        user_class(obj, Array)
        byte(0x5b) # [
        long(obj.size)
        obj.each { |item| dump(item, depth + 1) }
        write_ivars(ivars) unless ivars.empty?
      when Hash
        raise TypeError, "can't dump hash with default proc" if obj.default_proc
        ivars = ivars_of(obj)
        byte(0x49) unless ivars.empty?
        extended(obj)
        user_class(obj, Hash)
        byte(obj.default.nil? ? 0x7b : 0x7d) # { or }
        long(obj.size)
        obj.each do |key, value|
          dump(key, depth + 1)
          dump(value, depth + 1)
        end
        dump(obj.default, depth + 1) unless obj.default.nil?
        write_ivars(ivars) unless ivars.empty?
      when Class
        raise TypeError, "singleton class can't be dumped" if (obj.singleton_class? rescue false)
        byte(0x63) # c
        bytes(class_name(obj))
      when Module
        byte(0x6d) # m
        bytes(class_name(obj))
      when Struct
        byte(0x53) # S
        symbol(class_name(obj.class).to_sym)
        members = obj.members
        long(members.size)
        members.each do |member|
          symbol(member)
          dump(obj[member], depth + 1)
        end
      when Range
        byte(0x6f) # o
        symbol(class_name(obj.class).to_sym)
        write_ivars([[:excl, obj.exclude_end?], [:begin, obj.begin], [:end, obj.end]])
      when Exception
        byte(0x6f)
        symbol(class_name(obj.class).to_sym)
        write_ivars([[:mesg, obj.message], [:bt, obj.backtrace]] + ivars_of(obj))
      when Proc, Method, UnboundMethod, IO, Binding, Thread, Mutex
        raise TypeError, "no _dump_data is defined for class #{obj.class}"
      else
        extended(obj)
        byte(0x6f) # o
        symbol(class_name(obj.class).to_sym)
        write_ivars(ivars_of(obj))
      end
    end
  end

  class Loader
    def initialize(data, proc, freeze)
      @data = data.b
      @pos = 0
      @proc = proc
      @freeze = freeze
      @symbols = []
      @objects = []
    end

    def byte
      b = @data.getbyte(@pos)
      raise ArgumentError, "marshal data too short" if b.nil?
      @pos += 1
      b
    end

    def long
      c = byte
      c -= 256 if c > 127
      return 0 if c == 0
      return c - 5 if c > 4
      return c + 5 if c < -4
      if c > 0
        n = 0
        c.times { |i| n |= byte << (8 * i) }
        n
      else
        n = -1
        (-c).times do |i|
          n &= ~(0xff << (8 * i))
          n |= byte << (8 * i)
        end
        n
      end
    end

    def bytes
      length = long
      raise ArgumentError, "marshal data too short" if @pos + length > @data.bytesize
      string = @data.byteslice(@pos, length)
      @pos += length
      string
    end

    def symbol_body(ivars = false)
      index = @symbols.size
      @symbols << nil
      name = bytes
      if ivars
        long.times do
          key = read_symbol
          value = load
          name.force_encoding(Encoding::UTF_8) if key == :E && value
          name.force_encoding(value) if key == :encoding
        end
      end
      name.force_encoding(Encoding::UTF_8) unless ivars
      @symbols[index] = name.to_sym
    end

    def read_symbol
      case byte
      when 0x3a then symbol_body
      when 0x3b then @symbols.fetch(long)
      when 0x49
        raise ArgumentError, "dump format error (symlink with encoding)" unless byte == 0x3a
        symbol_body(true)
      else
        raise ArgumentError, "dump format error for symbol(0x#{@data.getbyte(@pos - 1).to_s(16)})"
      end
    end

    def find_class(name)
      Object.const_get(name.to_s)
    rescue NameError
      raise ArgumentError, "undefined class/module #{name}"
    end

    def register(obj)
      @objects << obj
      obj
    end

    def reserve
      index = @objects.size
      @objects << nil
      index
    end

    def finish(obj)
      obj = obj.freeze if @freeze && !obj.is_a?(Class) && !obj.is_a?(Module)
      obj = @proc.call(obj) if @proc
      obj
    end

    def set_ivars(obj)
      long.times do
        name = read_symbol
        value = load
        if obj.is_a?(String) || obj.is_a?(Regexp)
          target = obj.is_a?(Regexp) ? nil : obj
          if name == :E
            target&.force_encoding(value ? Encoding::UTF_8 : Encoding::US_ASCII)
            next
          elsif name == :encoding
            target&.force_encoding(value)
            next
          end
        end
        obj.instance_variable_set(name, value)
      end
    end

    def load(extends = [])
      type = byte
      case type
      when 0x30 then finish(nil)
      when 0x54 then finish(true)
      when 0x46 then finish(false)
      when 0x69 then finish(long)
      when 0x3a then finish(symbol_body)
      when 0x3b then finish(@symbols.fetch(long))
      when 0x40
        index = long
        raise ArgumentError, "dump format error (unlinked)" if index >= @objects.size
        @objects[index]
      when 0x49 # I: an object followed by ivars
        if @data.getbyte(@pos) == 0x3a
          byte
          return finish(symbol_body(true))
        end
        obj = load_object(byte, extends, true)
        finish(obj)
      when 0x65 # e
        mod = find_class(read_symbol)
        load(extends + [mod])
      else
        finish(load_object(type, extends, false))
      end
    end

    def load_object(type, extends, ivars)
      case type
      when 0x22 # "
        s = register(bytes.force_encoding(Encoding::ASCII_8BIT))
        set_ivars(s) if ivars
        extends.each { |m| s.extend(m) }
        s
      when 0x6c # l
        sign = byte
        count = long
        n = 0
        (count * 2).times { |i| n |= byte << (8 * i) }
        register(sign == 0x2d ? -n : n)
      when 0x66 # f
        text = bytes
        value = case text
                when "nan" then Float::NAN
                when "inf" then Float::INFINITY
                when "-inf" then -Float::INFINITY
                else Float(text.sub(/\0.*\z/m, ""))
                end
        register(value)
      when 0x5b # [
        array = register([])
        long.times { array << load }
        set_ivars(array) if ivars
        extends.each { |m| array.extend(m) }
        array
      when 0x7b, 0x7d # { }
        hash = register({})
        long.times do
          key = load
          hash[key] = load
        end
        hash.default = load if type == 0x7d
        set_ivars(hash) if ivars
        extends.each { |m| hash.extend(m) }
        hash
      when 0x2f # /
        source = bytes
        options = byte
        index = reserve
        source.force_encoding(Encoding::UTF_8)
        if ivars
          long.times do
            read_symbol
            load
          end
        end
        @objects[index] = Regexp.new(source, options)
      when 0x63 # c
        register(find_class(bytes))
      when 0x6d, 0x4d # m M
        register(find_class(bytes))
      when 0x53 # S
        klass = find_class(read_symbol)
        index = reserve
        values = {}
        long.times do
          name = read_symbol
          values[name] = load
        end
        @objects[index] = klass.new(*klass.members.map { |m| values[m] })
      when 0x6f # o
        klass = find_class(read_symbol)
        index = reserve
        if klass <= Range
          ivars = {}
          long.times { ivars[read_symbol] = load }
          return @objects[index] = Range.new(ivars[:begin], ivars[:end], ivars[:excl])
        end
        if klass <= Exception
          ivars = {}
          long.times { ivars[read_symbol] = load }
          error = klass.allocate
          error.__send__(:initialize, ivars.delete(:mesg))
          bt = ivars.delete(:bt)
          error.set_backtrace(bt) if bt
          ivars.each { |k, v| error.instance_variable_set(k, v) }
          return @objects[index] = error
        end
        obj = @objects[index] = klass.allocate
        set_ivars(obj)
        extends.each { |m| obj.extend(m) }
        obj
      when 0x75 # u
        klass = find_class(read_symbol)
        data = bytes
        set_ivars(data) if ivars
        unless klass.respond_to?(:_load, true)
          raise TypeError, "class #{klass} needs to have method '_load'"
        end
        register(klass.__send__(:_load, data))
      when 0x55 # U
        klass = find_class(read_symbol)
        index = reserve
        obj = klass.allocate
        @objects[index] = obj
        data = load
        unless obj.respond_to?(:marshal_load, true)
          raise TypeError, "instance of #{klass} needs to have method 'marshal_load'"
        end
        obj.__send__(:marshal_load, data)
        obj
      when 0x43 # C: a user subclass of String, Array, Hash or Regexp
        klass = find_class(read_symbol)
        inner_type = byte
        obj = load_object(inner_type, extends, ivars)
        converted = klass.allocate
        case obj
        when String then converted.replace(obj)
        when Array then converted.replace(obj)
        when Hash then converted.replace(obj)
        else return obj
        end
        @objects[@objects.index { |o| o.equal?(obj) } || @objects.size] = converted
        converted
      when 0x64 # d
        raise TypeError, "can't load data of class #{read_symbol}"
      else
        raise ArgumentError, "dump format error(0x#{type.to_s(16)})"
      end
    end
  end

  def self.dump(obj, io = nil, limit = -1)
    if io.is_a?(Integer)
      limit = io
      io = nil
    end
    dumper = Dumper.new(limit)
    dumper.byte(MAJOR_VERSION)
    dumper.byte(MINOR_VERSION)
    dumper.dump(obj)
    if io
      raise TypeError, "instance of IO needed" unless io.respond_to?(:write)
      io.write(dumper.out)
      io
    else
      dumper.out
    end
  end

  def self.load(source, proc = nil, freeze: false)
    data = if source.respond_to?(:to_str)
             source.to_str
           elsif source.respond_to?(:read)
             source.read
           else
             raise TypeError, "instance of IO needed"
           end
    raise ArgumentError, "marshal data too short" if data.nil? || data.bytesize < 2
    major = data.getbyte(0)
    minor = data.getbyte(1)
    if major != MAJOR_VERSION || minor > MINOR_VERSION
      raise TypeError, "incompatible marshal file format (can't be read)\n" \
                       "\tformat version #{MAJOR_VERSION}.#{MINOR_VERSION} required; #{major}.#{minor} given"
    end
    loader = Loader.new(data, proc, freeze)
    loader.instance_variable_set(:@pos, 2)
    loader.load
  end

  class << self
    alias restore load
  end
end
