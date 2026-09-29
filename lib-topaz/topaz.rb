module Topaz
  # Relative paths of loaded files are relative to this directory.
  STARTUP_DIR = Dir.pwd

  # Kernel#Integer's strict parse of a String: surrounding whitespace, a
  # sign, a base prefix and single underscores between digits; nil when
  # the string is not an integer.
  def self.strict_integer(str, base)
    raise ::ArgumentError, "string contains null byte" if str.include?("\0")
    s = str.strip
    negative = false
    if s.start_with?("+", "-")
      negative = s.start_with?("-")
      s = s[1..-1]
    end
    prefix_base = nil
    if s.length >= 2 && s[0] == "0"
      prefix_base = case s[1]
                    when "x", "X" then 16
                    when "b", "B" then 2
                    when "o", "O" then 8
                    when "d", "D" then 10
                    end
    end
    if prefix_base && (base == 0 || base == prefix_base)
      base = prefix_base
      s = s[2..-1]
    elsif base == 0
      base = s.length > 1 && s[0] == "0" ? 8 : 10
    end
    raise ::ArgumentError, "invalid radix #{base}" unless base.between?(2, 36)
    return nil if s.empty? || s.start_with?("_") || s.end_with?("_") || s.include?("__")
    digits = s.delete("_")
    digits.each_char do |c|
      d = c.to_i(36)
      return nil if d >= base || (d == 0 && c != "0")
    end
    value = digits.to_i(base)
    negative ? -value : value
  end

  def self.recursion_guard_outer(identifier, obj, &block)
    # We want to throw something less likely to be caught accidentally outside
    # our own code than the recursion identifier. Ideally this should be an
    # object that is unique to this particular recursion guard. Since doing
    # that properly requires pushing extra state all the way up into
    # ExecutionContext, we do this instead.
    throw_symbol = "__recursion_guard_#{identifier}".to_sym

    if Thread.current.in_recursion_guard?(identifier)
      Thread.current.recursion_guard(identifier, obj) do
        yield
        return false
      end
      throw(throw_symbol)
    else
      Thread.current.recursion_guard(identifier, obj) do
        catch(throw_symbol) do
          yield
          return false
        end
        return true
      end
    end
  end
end

lib_topaz = File.join(File.dirname(__FILE__), 'topaz')
load_bootstrap = proc do |file|
  load(File.join(lib_topaz, file))
end

load_bootstrap.call("array.rb")
