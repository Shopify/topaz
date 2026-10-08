class Struct
  include Enumerable

  class << self
    alias subclass_new new
  end

  def self.new(klass_name, *attrs, keyword_init: nil, &block)
    if klass_name
      begin
        klass_name = Topaz.convert_type(klass_name, String, :to_str)
      rescue TypeError
        attrs.unshift(klass_name)
        klass_name = nil
      end
    end

    attrs = attrs.map do |attr|
      case attr
      when String, Symbol
        Topaz.convert_type(attr, Symbol, :to_sym)
      else
        raise TypeError.new("#{attr.inspect} is not a symbol")
      end
    end

    klass = Class.new(self) do
      attr_accessor(*attrs)

      def self.new(*args, **kwargs, &block)
        return subclass_new(*args, **kwargs, &block)
      end

      def self.[](*args, **kwargs)
        return new(*args, **kwargs)
      end

      const_set(:STRUCT_ATTRS, attrs)
      # The fields live in instance variables; their names are built once
      # here rather than on every access.
      const_set(:STRUCT_IVARS, attrs.map { |attr| :"@#{attr}" })
      const_set(:STRUCT_KEYWORD_INIT, keyword_init.nil? ? nil : !!keyword_init)

      def self.keyword_init?
        self::STRUCT_KEYWORD_INIT
      end
    end

    Struct.const_set(klass_name, klass) if klass_name
    klass.module_eval(&block) if block
    klass
  end

  def self.make_struct(name, attrs)
    new(name, *attrs)
  end

  def instance_variables
    # Hide the ivars used to store the struct fields
    self.singleton_class.instance_variables - self.class::STRUCT_IVARS
  end

  # keyword_init: true takes only keywords, false only positional
  # arguments (a hash is one of them), and nil (the default) keywords when
  # there are no positional arguments.
  def initialize(*args, **kwargs)
    attrs = self.class::STRUCT_ATTRS
    keyword_init = self.class::STRUCT_KEYWORD_INIT
    if keyword_init == true && !args.empty?
      raise ArgumentError.new("wrong number of arguments (given #{args.size}, expected 0)")
    end
    if !kwargs.empty? && (keyword_init == true || (keyword_init.nil? && args.empty?))
      unknown = kwargs.keys.reject { |k| attrs.include?(k.to_sym) }
      raise ArgumentError.new("unknown keywords: #{unknown.join(", ")}") unless unknown.empty?
      ivars = self.class::STRUCT_IVARS
      attrs.each_with_index { |attr, i| instance_variable_set(ivars[i], kwargs[attr]) }
      return
    end
    args << kwargs unless kwargs.empty?

    unless args.length <= attrs.length
      raise ArgumentError.new("struct size differs")
    end

    ivars = self.class::STRUCT_IVARS
    i = 0
    while i < ivars.length
      instance_variable_set(ivars[i], args[i])
      i += 1
    end
  end

  private :initialize

  def ==(other)
    return false if self.class != other.class

    Thread.current.recursion_guard(:==, self) do
      return self.values == other.values
    end
    true
  end

  def eql?(other)
    return true if equal?(other)
    return false if self.class != other.class

    Thread.current.recursion_guard(:eql?, self) do
      self.class::STRUCT_IVARS.each do |ivar|
        mine = instance_variable_get(ivar)
        theirs = other.instance_variable_get(ivar)
        return false unless mine.eql?(theirs)
      end
    end
    true
  end

  def [](var)
    case var
    when Symbol, String
      idx = self.class::STRUCT_ATTRS.index(var.to_sym)
      raise NameError.new("no member '#{var}' in struct") unless idx
      return instance_variable_get(self.class::STRUCT_IVARS[idx])
    else
      var = Topaz.convert_type(var, Topaz::Fixnum, :to_int)
      a_len = self.class::STRUCT_ATTRS.length
      if var > a_len - 1
        raise IndexError.new("offset #{var} too large for struct(size:#{a_len})")
      end
      if var < -a_len
        raise IndexError.new("offset #{var + a_len} too small for struct(size:#{a_len})")
      end
      return instance_variable_get(self.class::STRUCT_IVARS[var])
    end
  end

  def []=(var, obj)
    case var
    when Symbol, String
      idx = self.class::STRUCT_ATTRS.index(var.to_sym)
      raise NameError, "no member '#{var}' in struct" unless idx
      return instance_variable_set(self.class::STRUCT_IVARS[idx], obj)
    else
      var = Topaz.convert_type(var, Topaz::Fixnum, :to_int)
      a_len = self.class::STRUCT_ATTRS.length
      if var > a_len - 1
        raise IndexError, "offset #{var} too large for struct(size:#{a_len})"
      end
      if var < -a_len
        raise IndexError, "offset #{var + a_len} too small for struct(size:#{a_len})"
      end
      return instance_variable_set(self.class::STRUCT_IVARS[var], obj)
    end
  end

  def each(&block)
    return to_enum(:each) unless block
    values.each(&block)
    self
  end

  def each_pair(&block)
    return to_enum(:each_pair) unless block
    ivars = self.class::STRUCT_IVARS
    self.class::STRUCT_ATTRS.each_with_index do |var, i|
      yield var, instance_variable_get(ivars[i])
    end
    self
  end

  def hash
    hash_val = size

    recursion = Thread.current.recursion_guard(:hash, self) do
      self.class::STRUCT_IVARS.each do |ivar|
        hash_val ^= instance_variable_get(ivar).hash
      end
    end

    hash_val
  end

  def length
    self.class::STRUCT_ATTRS.length
  end
  alias size length

  def self.length
    self::STRUCT_ATTRS.size
  end

  class << self
    alias size length
  end

  def self.members
    self::STRUCT_ATTRS.dup
  end

  def members
    self.class.members
  end

  def select(&block)
    to_a.select(&block)
  end

  def to_a
    self.class::STRUCT_IVARS.map { |ivar| instance_variable_get(ivar) }
  end
  alias values to_a

  def values_at(*args)
    to_a.values_at(*args)
  end

  def to_s
    recursion = Thread.current.recursion_guard(:to_s, self) do
      values = []

      ivars = self.class::STRUCT_IVARS
      self.class::STRUCT_ATTRS.each_with_index do |var, i|
        val = instance_variable_get(ivars[i])
        values << "#{var}=#{val.inspect}"
      end

      name = self.class.name

      if name.nil? || name.empty?
        return "#<struct #{values.join(', ')}>"
      else
        return "#<struct #{self.class.name} #{values.join(', ')}>"
      end
    end
    return "[...]" if recursion
  end
  alias inspect to_s

  Struct.new('Tms', :utime, :stime, :cutime, :cstime, :tutime, :tstime) do
    def initialize(utime=nil, stime=nil, cutime=nil, cstime=nil,
                   tutime=nil, tstime=nil)
      @utime = utime
      @stime = stime
      @cutime = cutime
      @cstime = cstime
      @tutime = tutime
      @tstime = tstime
    end
  end
end

class Struct
  def to_h(&block)
    pairs = members.zip(values)
    pairs = pairs.map(&block) if block
    pairs.to_h
  end
end
