module Kernel
  def puts(*args)
    $stdout.puts(*args)
  end
  private :puts

  def gets(sep = $/, limit = nil)
    $stdin.gets(sep, limit)
  end
  private :gets

  def print(*args)
    $stdout.print(*args)
  end
  private :print

  def p(*args)
    args.each { |arg| $stdout.print(arg.inspect + "\n") }
  end
  private :p

  def <=>(other)
    self == other ? 0 : nil
  end

  def chop
    $_.chop!
  end
  private :chop

  def chomp
    $_.chomp!
  end
  private :chomp

  def Array(arg)
    if ary = Topaz.try_convert_type(arg, Array, :to_ary)
      ary
    elsif arg.respond_to?(:to_a) && ary = Topaz.try_convert_type(arg, Array, :to_a)
      ary
    else
      [arg]
    end
  end
  private :Array

  def String(arg)
    Topaz.convert_type(arg, String, :to_s)
  end
  module_function :String
  private :String

  def Integer(arg, base = nil, exception: true)
    unless exception
      begin
        return Integer(arg, base)
      rescue ::ArgumentError, ::TypeError, ::FloatDomainError
        return nil
      end
    end
    if arg.kind_of?(String)
      value = Topaz.strict_integer(arg, base.nil? ? 0 : base)
      raise ArgumentError.new("invalid value for Integer(): #{arg.inspect}") if value.nil?
      return value
    end

    raise ArgumentError.new("base specified for non string value") if base
    return Topaz.convert_type(arg, Integer, :to_int) if arg.nil?

    if arg.respond_to?(:to_int) && val = arg.to_int
      return val
    end
    Topaz.convert_type(arg, Integer, :to_i)
  end

  module_function :Integer
  private :Integer

  def Float(arg, exception: true)
    unless exception
      begin
        return Float(arg)
      rescue ::ArgumentError, ::TypeError, ::RangeError
        return nil
      end
    end
    return Topaz.strict_float(arg) if arg.kind_of?(String)
    __topaz_Float(arg)
  end

  module_function :Float
  private :Float

  def loop(&block)
    return enum_for(:loop) unless block
    begin
      while true
        yield
      end
    rescue StopIteration
      nil
    end
    nil
  end
  private :loop

  def `(cmd)
    cmd = Topaz.convert_type(cmd, String, :to_str)
    res = nil
    IO.popen(cmd) do |r|
      res = r.read
      Process.waitpid(r.pid)
    end
    res.to_s
  end
  private :`

  # system and spawn are built from fork, exec and waitpid. Only the
  # :chdir and :exception options are supported; redirections are ignored.
  def spawn(*args)
    env = args.first.respond_to?(:to_hash) ? args.shift.to_hash : nil
    opts = args.last.respond_to?(:to_hash) ? args.pop.to_hash : {}
    raise ArgumentError, "wrong number of arguments (given 0, expected 1+)" if args.empty?
    Process.fork do
      env.each { |k, v| ENV[k] = v } if env
      Dir.chdir(opts[:chdir]) if opts[:chdir]
      begin
        exec(*args)
      rescue SystemCallError
        exit!(127)
      end
    end
  end
  private :spawn

  def system(*args)
    exception = false
    if args.last.respond_to?(:to_hash)
      opts = args.last.to_hash
      if opts.key?(:exception)
        opts = opts.dup
        exception = opts.delete(:exception)
        args = args[0...-1] + [opts]
      end
    end
    Process.waitpid(spawn(*args))
    status = $?
    if status.exitstatus == 127
      raise Errno::ENOENT, args.grep(String).first.to_s if exception
      return nil
    end
    if exception && !status.success?
      raise RuntimeError, "Command failed with exit #{status.exitstatus}: #{args.grep(String).join(" ")}"
    end
    status.success?
  end
  private :system

  def to_enum(method = :each, *args)
    Enumerator.new(self, method, *args)
  end
  ruby2_keywords :to_enum

  alias :enum_for :to_enum

  def rand(max = 1.0)
    if max.is_a?(Numeric)
      if max < 0
        return Random.rand(-max)
      elsif max.zero?
        return Random.rand
      elsif max.is_a?(Float) and max > 1
        return Random.rand(max).ceil
      end
    end
    Random.rand(max)
  end
  private :rand

  def caller(start = 1, length = nil)
    begin
      raise "caller called"
    rescue Exception => e
      # Leave out this method's own frame: trace[0] is its caller's.
      trace = e.backtrace[1..-1] || []
      return trace[start] if start.is_a?(Range)
      return length ? trace[start, length] : trace[start..-1]
    end
  end
  private :caller

  # A relative file name in a backtrace is relative to the directory the
  # program started in (the main script), not to the current directory.
  def require_relative(path)
    caller[0] =~ /^(.*):\d+:/
    caller_file = $1
    require File.expand_path(path, File.dirname(File.expand_path(caller_file, Topaz::STARTUP_DIR)))
  end

  def __dir__
    caller[0] =~ /^(.*):\d+:/
    caller_file = $1
    File.dirname(File.expand_path(caller_file, Topaz::STARTUP_DIR))
  end
end

module Kernel
  # Ruby 2.5/2.6
  def then
    return enum_for(:then) unless block_given?
    yield self
  end
  alias yield_self then

  # Ruby 2.2
  def itself
    self
  end

  # Ruby 2.5: pp works without requiring "pp".
  def pp(*args)
    p(*args)
  end
  private :pp
end

module Kernel
  # sprintf and format are in format.rb.
end

class LoadError
  # The feature that could not be loaded.
  attr_reader :path
end

module Kernel
  private :initialize_dup, :initialize_clone
end

class BasicObject
  private :method_missing
end
