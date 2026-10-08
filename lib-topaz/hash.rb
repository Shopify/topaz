class Hash
  def self.[](*args)
    if args.size == 1
      arg = args[0]
      if hash = Hash.try_convert(arg)
        return allocate.replace(hash)
      elsif array = Array.try_convert(arg)
        h = new
        array.each do |a|
          next unless a = Array.try_convert(a)
          next if a.size < 1 || a.size > 2
          h[a[0]] = a[1]
        end
        return h
      end
    end

    return new if args.empty?
    raise ArgumentError.new("odd number of arguments for Hash") if args.size.odd?

    h = new
    i = 0
    while i < args.size
      h[args[i]] = args[i + 1]
      i += 2
    end
    h
  end

  def each_key(&block)
    return self.enum_for(:each_key) if !block
    each { |k, v| yield k }
  end

  def each_value(&block)
    return self.enum_for(:each_value) if !block
    each { |k, v| yield v }
  end

  def to_a
    res = []
    each do |k, v|
      res << [k, v]
    end
    res
  end

  def ==(other)
    return true if self.equal?(other)
    return false unless other.kind_of?(Hash)
    return false unless self.size == other.size
    Thread.current.recursion_guard(:hash_compare, self) do
      self.each do |key, value|
        return false unless other.has_key?(key) && value == other[key]
      end
    end
    true
  end

  def eql?(other)
    return true if self.equal?(other)
    return false unless other.kind_of?(Hash)
    return false unless self.size == other.size
    Thread.current.recursion_guard(:hash_eql, self) do
      self.each do |key, value|
        return false unless other.has_key?(key) && value.eql?(other[key])
      end
    end
    true
  end

  def assoc(key)
    each do |k, v|
      return [k, v] if key == k
    end
    nil
  end

  def rassoc(value)
    each do |k, v|
      return [k, v] if value == v
    end
    nil
  end

  def value?(value)
    each do |k, v|
      return true if value == v
    end
    false
  end
  alias has_value? value?

  def values_at(*keys)
    keys.map { |k| self[k] }
  end

  def key(value)
    each_pair do |k, v|
      return k if v == value
    end
    nil
  end
  # TODO: Emit "warning: Hash#index is deprecated; use Hash#key" warning
  alias index key

  def except(*keys)
    result = dup
    keys.each { |key| result.delete(key) }
    result
  end

  def invert
    res = {}
    each do |k, v|
      res[v] = k
    end
    res
  end

  def inspect
    result = "{"
    recursion = Thread.current.recursion_guard(:hash_inspect, self) do
      self.each_with_index do |(key, value), i|
        if i > 0
          result << ", "
        end
        # Ruby 3.4: {a: 1, "+": 2, "b" => 3}
        if key.is_a?(Symbol)
          label = Topaz.label_symbol?(key) ? key.to_s : key.to_s.inspect
          result << "#{label}: #{value.inspect}"
        else
          result << "#{key.inspect} => #{value.inspect}"
        end
      end
    end
    if recursion
      result << "..."
    end
    result << "}"
  end

  alias :to_s :inspect

  # select!/filter!/keep_if and reject!/delete_if are RPython (hashobject.py).

  def select(&block)
    return enum_for(:select) unless block
    dup.keep_if(&block)
  end

  def reject(&block)
    return enum_for(:reject) unless block
    dup.delete_if(&block)
  end

  def flatten(level = 1)
    level = Topaz.convert_type(level, Topaz::Fixnum, :to_int)
    to_a.flatten(level)
  end

  def self.try_convert(arg)
    Topaz.try_convert_type(arg, Hash, :to_hash)
  end
end

class Hash
  alias filter select
  alias filter! select!

  # Ruby 2.4
  def transform_values(&block)
    return enum_for(:transform_values) unless block
    result = {}
    each_pair { |key, value| result[key] = yield(value) }
    result
  end

  def transform_values!(&block)
    return enum_for(:transform_values!) unless block
    each_pair { |key, value| self[key] = yield(value) }
    self
  end

  # Ruby 2.5; the hash argument is Ruby 3.0
  def transform_keys!(mapping = nil, &block)
    return enum_for(:transform_keys!) unless block || mapping
    replace(mapping ? transform_keys(mapping, &block) : transform_keys(&block))
  end

  # Ruby 2.5
  def slice(*keys)
    result = {}
    keys.each { |key| result[key] = self[key] if key?(key) }
    result
  end

  # Ruby 2.3
  def dig(key, *rest)
    item = self[key]
    rest.empty? || item.nil? ? item : item.dig(*rest)
  end

  # Ruby 2.4
  def compact
    reject { |key, value| value.nil? }
  end

  def compact!
    size_before = size
    delete_if { |key, value| value.nil? }
    size_before == size ? nil : self
  end

  # Ruby 2.3
  def fetch_values(*keys, &block)
    keys.map { |key| fetch(key, &block) }
  end
end

