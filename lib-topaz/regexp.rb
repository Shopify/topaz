class Regexp
  def to_regexp
    self
  end

  def hash
    to_s.hash
  end

  def ~
    self =~ $_
  end

  def self.try_convert(arg)
    Topaz.try_convert_type(arg, Regexp, :to_regexp)
  end
end

class Regexp
  def self.union(*patterns)
    patterns = patterns[0] if patterns.size == 1 && patterns[0].is_a?(Array)
    return /(?!)/ if patterns.empty?
    if patterns.size == 1
      pattern = patterns[0]
      return pattern if pattern.is_a?(Regexp)
      return new(escape(Topaz.convert_type(pattern, String, :to_str)))
    end
    source = patterns.map do |pattern|
      if pattern.is_a?(Regexp)
        pattern.to_s
      else
        escape(Topaz.convert_type(pattern, String, :to_str))
      end
    end
    new(source.join("|"))
  end
end

class Regexp
  def inspect
    flags = ""
    flags << "m" if options & MULTILINE != 0
    flags << "i" if options & IGNORECASE != 0
    flags << "x" if options & EXTENDED != 0
    "/#{source.gsub(%r{(?<!\\)/}, "\\/")}/#{flags}"
  end
end
