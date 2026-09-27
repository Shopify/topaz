# The Warning module (Ruby 2.4), and Kernel#warn going through it.

module Warning
  CATEGORIES = [:deprecated, :experimental, :performance, :strict_unused_block]
  @deprecated = false
  @experimental = true
  @performance = false
  @strict_unused_block = false

  def self.[](category)
    unless CATEGORIES.include?(category)
      raise ArgumentError.new("unknown category: #{category}")
    end
    instance_variable_get("@#{category}")
  end

  def self.[]=(category, value)
    unless CATEGORIES.include?(category)
      raise ArgumentError.new("unknown category: #{category}")
    end
    instance_variable_set("@#{category}", value)
  end

  # Ruby 3.4
  def self.categories
    CATEGORIES.dup
  end

  def warn(message, category: nil)
    unless message.is_a?(String)
      raise TypeError.new("wrong argument type #{message.class} (expected String)")
    end
    $stderr.write(message)
    nil
  end
  module_function :warn
  public :warn
end

module Kernel
  def warn(*messages, uplevel: nil, category: nil)
    return nil if $VERBOSE.nil? || messages.empty?
    lines = messages.flatten.map do |message|
      message = message.to_s
      message.end_with?("\n") ? message : message + "\n"
    end
    text = lines.join
    if uplevel
      location = caller(uplevel + 1, 1).first
      if location
        location = location.sub(/:in .*\z/, "")
        text = "#{location}: warning: #{text}"
      end
    end
    if category.nil?
      Warning.warn(text)
    else
      Warning.warn(text, category: category)
    end
    nil
  end
  private :warn
end
