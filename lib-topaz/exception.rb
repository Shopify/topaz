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
