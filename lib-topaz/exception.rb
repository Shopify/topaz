class FrozenError < RuntimeError
  def initialize(message = nil, receiver: nil)
    super(message)
    @receiver = receiver
  end

  def receiver
    @receiver
  end
end

class Exception
  # The Ruby 3.4 format.
  def inspect
    klass = self.class.to_s
    msg = to_s
    return klass if msg.empty?
    return "#<#{klass}:#{msg.inspect}>" if msg.include?("\n")
    "#<#{klass}: #{msg}>"
  end

  def detailed_message(highlight: false, **opts)
    msg = message.to_s
    msg = "unhandled exception" if msg.empty?
    "#{msg} (#{self.class})"
  end

  def full_message(highlight: false, order: :top, **opts)
    trace = backtrace || []
    out = "#{trace.first ? "#{trace.first}: " : ""}#{detailed_message(highlight: highlight)}"
    trace.drop(1).each { |line| out << "\n\tfrom #{line}" }
    out + "\n"
  end

  def backtrace_locations
    nil
  end
end

class NameError
  alias __topaz_initialize initialize
  private :__topaz_initialize

  def initialize(message = nil, name = nil, receiver: (no_receiver = true; nil))
    __topaz_initialize(message, name)
    @__topaz_receiver = receiver unless no_receiver
  end

  def receiver
    unless instance_variable_defined?(:@__topaz_receiver)
      raise ArgumentError, "no receiver is available"
    end
    @__topaz_receiver
  end

  def local_variables
    []
  end
end

class NoMethodError
  def initialize(message = nil, name = nil, args = [], priv = false, receiver: (no_receiver = true; nil))
    __topaz_initialize(message, name)
    @__topaz_receiver = receiver unless no_receiver
    @__topaz_args = args
    @__topaz_private_call = priv
  end

  def args
    @__topaz_args || []
  end

  def private_call?
    @__topaz_private_call ? true : false
  end
end
