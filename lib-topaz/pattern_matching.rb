# Support for pattern matching (Ruby 2.7/3.0). The patterns themselves are
# compiled by topaz/prism/translate.py into calls to the methods below.

class NoMatchingPatternError < StandardError
end

class NoMatchingPatternKeyError < NoMatchingPatternError
  attr_reader :matchee, :key

  def initialize(message = nil, matchee: nil, key: nil)
    super(message)
    @matchee = matchee
    @key = key
  end
end

class Array
  def deconstruct
    self
  end
end

class Hash
  def deconstruct_keys(keys)
    self
  end
end

class Struct
  def deconstruct
    to_a
  end

  def deconstruct_keys(keys)
    result = {}
    members.each do |member|
      result[member] = self[member] if keys.nil? || keys.include?(member)
    end
    result
  end
end
