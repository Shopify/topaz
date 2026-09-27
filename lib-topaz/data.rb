# Data (Ruby 3.2): immutable value objects.
#
#   Point = Data.define(:x, :y)
#   Point.new(1, 2) == Point.new(x: 1, y: 2)   # => true

class Data
  class << self
    undef_method :new

    def define(*members, &block)
      members = members.map do |member|
        member = member.to_sym if member.is_a?(String)
        unless member.is_a?(Symbol)
          raise TypeError.new("#{member.inspect} is not a symbol nor a string")
        end
        member
      end
      if members.uniq.size != members.size
        duplicate = members.find { |m| members.count(m) > 1 }
        raise ArgumentError.new("duplicate member: #{duplicate}")
      end

      klass = Class.new(Data)
      klass.instance_variable_set(:@__members__, members.freeze)
      class << klass
        def new(*args, **kwargs)
          members = self.members
          unless args.empty?
            if args.size > members.size
              raise ArgumentError.new(
                "wrong number of arguments (given #{args.size}, expected 0..#{members.size})")
            end
            positional = {}
            args.each_with_index { |arg, i| positional[members[i]] = arg }
            kwargs = positional.merge(kwargs)
          end
          obj = allocate
          obj.send(:initialize, **kwargs)
          obj.freeze
        end
        alias_method :[], :new

        def members
          @__members__
        end
      end
      members.each do |member|
        klass.send(:define_method, member) { @__attributes__[member] }
      end
      klass.class_eval(&block) if block
      klass
    end
  end

  def initialize(**kwargs)
    members = self.class.members
    missing = members - kwargs.keys
    unless missing.empty?
      raise ArgumentError.new(
        "missing keyword#{missing.size > 1 ? 's' : ''}: #{missing.map(&:inspect).join(', ')}")
    end
    unknown = kwargs.keys - members
    unless unknown.empty?
      raise ArgumentError.new(
        "unknown keyword#{unknown.size > 1 ? 's' : ''}: #{unknown.map(&:inspect).join(', ')}")
    end
    @__attributes__ = {}
    members.each { |member| @__attributes__[member] = kwargs[member] }
  end

  def members
    self.class.members
  end

  def to_h(&block)
    result = {}
    members.each { |member| result[member] = @__attributes__[member] }
    block ? result.to_h(&block) : result
  end

  def deconstruct
    members.map { |member| @__attributes__[member] }
  end

  def deconstruct_keys(keys)
    keys.nil? ? to_h : to_h.slice(*keys)
  end

  def with(**changes)
    return self if changes.empty?
    self.class.new(**to_h.merge(changes))
  end

  def ==(other)
    other.class == self.class && other.to_h == to_h
  end

  def eql?(other)
    other.class == self.class &&
      members.all? { |m| @__attributes__[m].eql?(other.send(m)) }
  end

  def hash
    [self.class, to_h].hash
  end

  def inspect
    name = self.class.name
    fields = members.map { |m| "#{m}=#{@__attributes__[m].inspect}" }
    parts = ["#<data"]
    parts << name if name
    parts << fields.join(", ") unless fields.empty?
    parts.join(" ") + ">"
  end
  alias to_s inspect
end
