# Core methods from Ruby 2.x to 4.0 that topaz did not have, written in Ruby.

class Module
  def deprecate_constant(*names)
    self
  end

  def public_constant(*names)
    self
  end

  def const_source_location(name, inherit = true)
    const_defined?(name, inherit) ? [] : nil
  end

  def included_modules
    ancestors.reject { |m| m.is_a?(Class) }
  end

  def undefined_instance_methods
    []
  end

  def public_instance_method(name)
    unless public_method_defined?(name)
      raise NameError.new("undefined public method '#{name}' for #{inspect}", name)
    end
    instance_method(name)
  end

  def set_temporary_name(name)
    self
  end

  def refinements
    (@__topaz_refinements || {}).values
  end

  private

  def const_added(name)
    nil
  end

  # Refinements, approximately: topaz has no lexically scoped method
  # tables, so a refinement's methods are made visible everywhere, as a
  # module included into the refined class. The class's own methods win
  # over them, so a refinement can add methods but not override the
  # class's; `using` does nothing.
  def refine(klass, &block)
    raise ArgumentError, "no block given" unless block
    unless klass.is_a?(Module)
      raise TypeError, "wrong argument type #{klass.class} (expected Class or Module)"
    end
    @__topaz_refinements ||= {}
    refinement = @__topaz_refinements[klass] ||= begin
      mod = Module.new
      mod.instance_variable_set(:@__topaz_refined_class, klass)
      mod.define_singleton_method(:target) { klass }
      mod
    end
    refinement.module_eval(&block)
    klass.__send__(:include, refinement) unless klass.include?(refinement) || klass.equal?(refinement)
    refinement
  end

  def using(mod)
    self
  end
end

module Kernel
  def public_send(name, *args, &block)
    unless respond_to?(name)
      if respond_to?(name, true)
        raise NoMethodError.new("private method '#{name}' called for #{Topaz.inspect_for_error(self)}", name)
      end
    end
    __send__(name, *args, &block)
  end
  ruby2_keywords :public_send

  def public_method(name)
    method(name)
  end

  def singleton_method(name)
    unless singleton_methods.include?(name.to_sym)
      raise NameError.new("undefined singleton method '#{name}' for #{inspect}", name)
    end
    method(name)
  end

  def display(port = $stdout)
    port.write(self)
    nil
  end

  def caller_locations(start = 1, length = nil)
    lines = caller(start + 1, length)
    return nil if lines.nil?
    lines.map { |line| Thread::Backtrace::Location.__topaz_parse(line) }
  end
  private :caller_locations

  def printf(*args)
    return nil if args.empty?
    if args[0].is_a?(String)
      $stdout.write(format(*args))
    else
      io = args.shift
      io.write(format(*args))
    end
    nil
  end
  private :printf

  def putc(c)
    $stdout.putc(c)
  end
  private :putc

  def readlines(*args)
    $stdin.readlines(*args)
  end
  private :readlines

  def readline(*args)
    line = gets(*args)
    raise EOFError, "end of file reached" if line.nil?
    line
  end
  private :readline

  def open(path, *args, &block)
    if path.respond_to?(:to_open)
      return path.to_open(*args, &block)
    end
    path = path.to_path if path.respond_to?(:to_path)
    if path.is_a?(String) && path.start_with?("|")
      return IO.popen(path[1..], *args, &block)
    end
    File.open(path, *args, &block)
  end
  ruby2_keywords :open
  private :open

  def Hash(arg)
    return {} if arg.nil? || arg == []
    Topaz.convert_type(arg, Hash, :to_hash)
  end
  private :Hash

  def trap(signal, command = nil, &block)
    Signal.trap(signal, command, &block)
  end
  private :trap

  def select(*args)
    IO.select(*args)
  end
  private :select

  def local_variables
    []
  end
  private :local_variables
end

module Topaz
  def self.inspect_for_error(obj)
    case obj
    when nil then "nil"
    when true then "true"
    when false then "false"
    when Module then "#{obj.is_a?(Class) ? "class" : "module"} #{obj}"
    else "an instance of #{obj.class}"
    end
  end
end

class Thread
  module Backtrace
    class Location
      attr_reader :path, :lineno, :label

      def self.__topaz_parse(line)
        if line =~ /\A(.*?):(\d+):in [`'](.*)'\z/
          new($1, $2.to_i, $3)
        elsif line =~ /\A(.*?):(\d+)/
          new($1, $2.to_i, nil)
        else
          new(line, 0, nil)
        end
      end

      def initialize(path, lineno, label)
        @path = path
        @lineno = lineno
        @label = label
      end

      def base_label
        return nil if @label.nil?
        label = @label.sub(/\Ablock (\(\d+ levels\) )?in /, "")
        label.split(/[#.]/).last
      end

      def absolute_path
        File.expand_path(@path, Topaz::STARTUP_DIR)
      end

      def to_s
        @label ? "#{@path}:#{@lineno}:in '#{@label}'" : "#{@path}:#{@lineno}"
      end

      def inspect
        to_s.inspect
      end
    end
  end

  def self.each_caller_location
    caller_locations(2).each { |location| yield location }
    nil
  end
end

module Signal
  def self.trap(signal, command = nil, &block)
    "DEFAULT"
  end

  def self.list
    {"EXIT" => 0, "HUP" => 1, "INT" => 2, "QUIT" => 3, "KILL" => 9, "USR1" => 10,
     "SEGV" => 11, "USR2" => 12, "PIPE" => 13, "ALRM" => 14, "TERM" => 15, "CHLD" => 17}
  end

  def self.signame(signo)
    list.key(signo)
  end
end

class String
  # gsub! and sub! are in RPython (stringobject.py), so that they set the
  # caller's $~.

  def lstrip
    i = 0
    n = bytesize
    while i < n
      b = getbyte(i)
      break unless b == 32 || (b >= 9 && b <= 13) || b == 0
      i += 1
    end
    byteslice(i, n - i)
  end

  def lstrip!
    result = lstrip
    return nil if result == self
    replace(result)
  end

  def center(width, padding = " ")
    width = Topaz.convert_type(width, Integer, :to_int)
    raise ArgumentError, "zero width padding" if padding.empty?
    n = width - length
    return dup if n <= 0
    left = n / 2
    right = n - left
    (padding * (left / padding.length + 1))[0, left] + self + (padding * (right / padding.length + 1))[0, right]
  end

  def partition(sep)
    if sep.is_a?(Regexp)
      m = sep.match(self)
      return [dup, "", ""] if m.nil?
      [m.pre_match, m[0], m.post_match]
    else
      sep = Topaz.convert_type(sep, String, :to_str)
      i = index(sep)
      return [dup, "", ""] if i.nil?
      [self[0, i], sep.dup, self[i + sep.length..-1]]
    end
  end

  def rpartition(sep)
    if sep.is_a?(Regexp)
      pos = length
      while pos >= 0
        m = sep.match(self, pos)
        if m && m.begin(0) == pos
          return [self[0, pos], m[0], self[pos + m[0].length..-1]]
        end
        pos -= 1
      end
      ["", "", dup]
    else
      sep = Topaz.convert_type(sep, String, :to_str)
      i = rindex(sep)
      return ["", "", dup] if i.nil?
      [self[0, i], sep.dup, self[i + sep.length..-1]]
    end
  end

  def codepoints
    return bytes unless encoding == Encoding::UTF_8 && valid_encoding?
    unpack("U*")
  end

  def each_codepoint(&block)
    return enum_for(:each_codepoint) unless block
    codepoints.each(&block)
    self
  end

  def grapheme_clusters
    chars
  end

  def each_grapheme_cluster(&block)
    return enum_for(:each_grapheme_cluster) unless block
    chars.each(&block)
    self
  end

  def byteindex(sub, offset = 0)
    sub = Topaz.convert_type(sub, String, :to_str) unless sub.is_a?(Regexp)
    b.index(sub.is_a?(Regexp) ? sub : sub.b, offset)
  end

  def byterindex(sub, offset = bytesize)
    b.rindex(sub.is_a?(Regexp) ? sub : Topaz.convert_type(sub, String, :to_str).b, offset)
  end

  def append_as_bytes(*objs)
    objs.each { |o| self << (o.is_a?(Integer) ? (o & 0xff).chr : o.to_s) }
    self
  end

  def dump
    inspect
  end

  def undump
    raise RuntimeError, "invalid dumped string" unless start_with?('"') && end_with?('"')
    eval(self)
  end

  # Character sets as tr, delete, count and squeeze take them: "a-z",
  # "^aeiou", and the intersection of several.
  def self.__topaz_charset(sets)
    tables = sets.map do |set|
      set = Topaz.convert_type(set, String, :to_str)
      negate = set.length > 1 && set.start_with?("^")
      set = set[1..] if negate
      chars = []
      i = 0
      cs = set.chars
      while i < cs.size
        if i + 2 < cs.size && cs[i + 1] == "-"
          lo = cs[i].ord
          hi = cs[i + 2].ord
          raise ArgumentError, "invalid range \"#{cs[i]}-#{cs[i + 2]}\" in string transliteration" if lo > hi
          (lo..hi).each { |c| chars << c }
          i += 3
        else
          chars << cs[i].ord
          i += 1
        end
      end
      [negate, chars]
    end
    lambda do |cp|
      tables.all? { |negate, chars| chars.include?(cp) != negate }
    end
  end

  def delete(*sets)
    raise ArgumentError, "wrong number of arguments (given 0, expected 1+)" if sets.empty?
    matcher = String.__topaz_charset(sets)
    chars.reject { |c| matcher.call(c.ord) }.join
  end

  def delete!(*sets)
    result = delete(*sets)
    return nil if result == self
    replace(result)
  end

  def count(*sets)
    raise ArgumentError, "wrong number of arguments (given 0, expected 1+)" if sets.empty?
    matcher = String.__topaz_charset(sets)
    n = 0
    each_char { |c| n += 1 if matcher.call(c.ord) }
    n
  end

  def crypt(salt)
    raise NotImplementedError, "String#crypt is not supported by topaz"
  end
end

class Symbol
  def match?(pattern, pos = 0)
    to_s.match?(pattern, pos)
  end

  def casecmp?(other)
    return nil unless other.is_a?(Symbol)
    to_s.casecmp?(other.to_s)
  end
end

class Regexp
  def match?(str, pos = 0)
    return false if str.nil?
    saved = $~
    result = !match(str.is_a?(Symbol) ? str.to_s : str, pos).nil?
    $~ = saved
    result
  end

  # names and named_captures are in RPython (regexpobject.py).

  def self.last_match(n = nil)
    m = $~
    return m if n.nil? || m.nil?
    m[n]
  end

  def timeout
    nil
  end

  def self.timeout
    nil
  end

  def self.timeout=(value)
    value
  end

  def self.linear_time?(*args)
    false
  end
end

class String
  def match?(pattern, pos = 0)
    pattern = Regexp.new(Regexp.escape(pattern)) if pattern.is_a?(String)
    pattern.match?(self, pos)
  end
end

class MatchData
  def names
    regexp.names
  end

  def named_captures(symbolize_names: false)
    result = {}
    names.each do |name|
      result[symbolize_names ? name.to_sym : name] = self[name]
    end
    result
  end

  def deconstruct
    captures
  end

  def deconstruct_keys(keys)
    result = {}
    names.each do |name|
      key = name.to_sym
      result[key] = self[name] if keys.nil? || keys.include?(key)
    end
    result
  end

  def match(n)
    self[n]
  end

  def match_length(n)
    s = self[n]
    s && s.length
  end

  def byteoffset(n)
    [self.begin(n), self.end(n)]
  end

  def bytebegin(n)
    self.begin(n)
  end

  def byteend(n)
    self.end(n)
  end
end

module Enumerable
  def grep_v(pattern, &block)
    result = []
    each do |*args|
      value = args.size == 1 ? args[0] : args
      unless pattern === value
        result << (block ? block.call(value) : value)
      end
    end
    result
  end

  def slice_after(pattern = nil, &block)
    raise ArgumentError, "both pattern and block are given" if pattern && block
    matcher = block || ->(x) { pattern === x }
    Enumerator.new do |y|
      current = []
      each do |x|
        current << x
        if matcher.call(x)
          y << current
          current = []
        end
      end
      y << current unless current.empty?
    end
  end

  def chain(*others)
    sources = [self] + others
    Enumerator.new do |y|
      sources.each { |source| source.each { |x| y << x } }
    end
  end
end

class Enumerator
  def +(other)
    chain(other)
  end
end

class Array
  def bsearch_index(&block)
    return enum_for(:bsearch_index) unless block
    low = 0
    high = size
    found = nil
    while low < high
      mid = low + (high - low) / 2
      r = block.call(self[mid])
      if r == true
        found = mid
        high = mid
      elsif r == false || r.nil?
        low = mid + 1
      elsif r.is_a?(Numeric)
        return mid if r == 0
        if r > 0
          low = mid + 1
        else
          high = mid
        end
      else
        raise TypeError, "wrong argument type #{r.class} (must be numeric, true, false or nil)"
      end
    end
    found
  end
end

class Range
  def bsearch(&block)
    return enum_for(:bsearch) unless block
    raise TypeError, "can't do binary search for #{self.begin.class}" unless self.begin.is_a?(Integer)
    low = self.begin
    high = exclude_end? ? self.end : self.end + 1
    found = nil
    while low < high
      mid = low + (high - low) / 2
      r = block.call(mid)
      if r == true || r == 0
        found = mid
        return mid if r == 0
        high = mid
      elsif r.is_a?(Numeric)
        r > 0 ? low = mid + 1 : high = mid
      else
        low = mid + 1
      end
    end
    found
  end
end

class Hash
  def <=(other)
    other = Topaz.convert_type(other, Hash, :to_hash)
    return false if size > other.size
    all? { |k, v| other.key?(k) && other[k] == v }
  end

  def <(other)
    other = Topaz.convert_type(other, Hash, :to_hash)
    size < other.size && self <= other
  end

  def >=(other)
    Topaz.convert_type(other, Hash, :to_hash) <= self
  end

  def >(other)
    Topaz.convert_type(other, Hash, :to_hash) < self
  end

  def to_proc
    method(:[]).to_proc
  end
end

class NilClass
  def to_h
    {}
  end
end

class Numeric
  def positive?
    self > 0
  end

  def negative?
    self < 0
  end

  def finite?
    true
  end

  def infinite?
    nil
  end

  def real?
    true
  end

  def real
    self
  end

  def imaginary
    0
  end
  alias imag imaginary

  def conj
    self
  end
  alias conjugate conj

  def abs2
    self * self
  end

  def remainder(other)
    r = self % other
    r != 0 && (self < 0) != (other < 0) ? r - other : r
  end

  def fdiv(other)
    to_f / other
  end

  def magnitude
    abs
  end

  def step(limit = nil, step = 1, by: nil, to: nil, &block)
    step = by if by
    limit = to if to
    return enum_for(:step, limit, step) unless block
    raise ArgumentError, "step can't be 0" if step == 0
    i = self
    if limit.nil?
      loop do
        block.call(i)
        i += step
      end
    elsif step > 0
      while i <= limit
        block.call(i)
        i += step
      end
    else
      while i >= limit
        block.call(i)
        i += step
      end
    end
    self
  end
end

class Float
  def positive?
    self > 0.0
  end

  def negative?
    self < 0.0
  end

  def fdiv(other)
    self / other
  end

  def magnitude
    abs
  end
end

class Struct
  def dig(key, *rest)
    value = self[key]
    return value if rest.empty? || value.nil?
    value.dig(*rest)
  end
end

class UnboundMethod
  def bind_call(receiver, *args, &block)
    bind(receiver).call(*args, &block)
  end
  ruby2_keywords :bind_call

  def original_name
    name
  end

  def super_method
    nil
  end
end

class Method
  def original_name
    name
  end

  def super_method
    nil
  end
end

module ObjectSpace
  def self.define_finalizer(obj, callable = nil, &block)
    [0, callable || block]
  end

  def self.undefine_finalizer(obj)
    obj
  end

  def self.count_objects(result = {})
    result
  end

  def self.garbage_collect(**opts)
    nil
  end
end

class Fiber
  # Fiber storage (Ruby 3.2). New fibers do not inherit it yet.
  def self.__topaz_storage
    respond_to?(:current) ? current.storage : (@__topaz_main_storage ||= {})
  end

  def self.[](key)
    __topaz_storage[key]
  end

  def self.[]=(key, value)
    storage = __topaz_storage
    if value.nil?
      storage.delete(key)
    else
      storage[key] = value
    end
    value
  end

  def storage
    @__topaz_storage ||= {}
  end

  def storage=(hash)
    @__topaz_storage = hash.to_h
  end
end

module Kernel
  # Pathname is autoloaded (it is core in Ruby 4.0).
  def Pathname(path)
    return path if path.is_a?(Pathname)
    Pathname.new(path)
  end
  private :Pathname
end

class String
  alias __topaz_initialize initialize
  private :__topaz_initialize

  # String.new(str = "", encoding: nil, capacity: nil). With no string
  # the new string is binary, as in CRuby.
  def initialize(*args, encoding: nil, capacity: nil)
    __topaz_initialize(*args)
    if encoding
      force_encoding(encoding)
    elsif args.empty?
      force_encoding(Encoding::ASCII_8BIT)
    end
    self
  end
  private :initialize
end

module Kernel
  # main.using: refinements are always on in topaz (see Module#refine).
  def using(mod)
    self
  end
  private :using
end

class Module
  alias __topaz_const_get const_get
  alias __topaz_const_defined? const_defined?
  private :__topaz_const_get, :__topaz_const_defined?

  # const_get and const_defined? take a path ("A::B::C"; a leading "::"
  # starts from Object).
  def const_get(name, inherit = true)
    return __topaz_const_get(name, inherit) unless name.is_a?(String) && name.include?("::")
    mod = self
    parts = name.split("::")
    if parts.first == ""
      mod = Object
      parts.shift
    end
    parts.each do |part|
      raise NameError.new("wrong constant name #{name}", name) if part.empty?
      mod = mod.__send__(:__topaz_const_get, part, inherit)
    end
    mod
  end

  def const_defined?(name, inherit = true)
    return __topaz_const_defined?(name, inherit) unless name.is_a?(String) && name.include?("::")
    mod = self
    parts = name.split("::")
    if parts.first == ""
      mod = Object
      parts.shift
    end
    parts.each_with_index do |part, i|
      raise NameError.new("wrong constant name #{name}", name) if part.empty?
      return false unless mod.__send__(:__topaz_const_defined?, part, inherit)
      return true if i == parts.size - 1
      mod = mod.__send__(:__topaz_const_get, part, inherit)
      return false unless mod.is_a?(Module)
    end
    true
  end
end

class Module
  alias __topaz_autoload? autoload?
  private :__topaz_autoload?

  # autoload?(name, inherit = true): with inherit, ancestors are asked too.
  def autoload?(name, inherit = true)
    path = __topaz_autoload?(name)
    return path if path || !inherit
    ancestors.drop(1).each do |mod|
      path = mod.__send__(:__topaz_autoload?, name)
      return path if path
    end
    nil
  end
end
