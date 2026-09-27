class Enumerator
  include Enumerable

  def initialize(obj = nil, method = :each, *args, &block)
    obj = Generator.new(&block) if obj.nil?

    @object = obj
    @method = method.to_sym
    @args = args
    self
  end

  def each(&block)
    if block
      @object.send(@method, *@args, &block)
    else
      self
    end
  end

  def each_with_index(&block)
    return self.enum_for(:each_with_index) unless block

    i = 0
    self.each do |*e|
      v = (e.size == 1) ? e[0] : e
      val = yield(v, i)
      i += 1
      val
    end
  end

  def with_index(offset = nil, &block)
    return self.enum_for(:with_index, offset) unless block
    offset = offset ? Topaz.convert_type(offset, Topaz::Fixnum, :to_int) : 0

    i = offset
    self.each do |*e|
      v = (e.size == 1) ? e[0] : e
      val = yield(v, i)
      i += 1
      val
    end
  end

  def rewind
    @object.rewind if @object.respond_to?(:rewind)
    @nextvals = nil
    @fiber = nil
    @finished = false
    self
  end

  def peek
    if @nextvals.nil?
      @nextvals = []
      @finished = false
      @fiber ||= Fiber.new do
        self.each do |*values|
          Fiber.yield(*values)
        end
        @finished = true
      end
    end

    if @nextvals.empty?
      @nextvals << @fiber.resume
      raise StopIteration.new("iteration reached an end") if @finished
    end

    return @nextvals.first
  end

  def peek_values
    return Array(self.peek)
  end

  def next
    raise StopIteration.new("iteration reached an end") if @finished
    self.peek
    return @nextvals.shift
  end

  def next_values
    return Array(self.next)
  end

  def with_object(obj, &block)
    return Enumerator.new(self, :with_object, obj) unless block
    self.each { |*v| yield(*v, obj) }
    return obj
  end

  class Generator
    include Enumerable

    def initialize(&block)
      @block = block
      self
    end

    def each
      proc = Proc.new { |*args| yield(*args) }
      @block.call(Yielder.new(&proc))
    end
  end

  class Yielder
    def initialize(&block)
      @block = block
      self
    end

    def yield(*args)
      @block.call(*args)
    end

    def <<(val)
      self.yield val
      self
    end
  end
end

class Enumerator
  # Ruby 2.7
  def self.produce(initial = (no_initial = true; nil), &block)
    raise ArgumentError.new("no block given") unless block
    Enumerator.new do |yielder|
      value = no_initial ? block.call(nil) : initial
      loop do
        yielder << value
        value = block.call(value)
      end
    end
  end

  # Enumerator::Lazy (Ruby 2.0): each step pulls values through the chain
  # one at a time, so infinite sources work.
  class Lazy < Enumerator
    def self.__from(&each_body)
      lazy = allocate
      lazy.__set_each_body(each_body)
      lazy
    end

    def initialize(obj, size = nil, &block)
      raise ArgumentError.new("tried to call lazy new without a block") unless block
      @each_body = proc do |blk|
        yielder = Yielder.new(&blk)
        obj.each { |*values| block.call(yielder, *values) }
      end
    end

    def __set_each_body(each_body)
      @each_body = each_body
    end

    def each(&blk)
      return self unless blk
      @each_body.call(blk)
      self
    end

    def lazy
      self
    end

    def eager
      lazy = self
      Enumerator.new { |yielder| lazy.each { |*values| yielder.yield(*values) } }
    end

    alias force to_a

    def first(*args)
      return super if args.empty?
      take(*args).to_a
    end

    def map(&block)
      Lazy.new(self) { |yielder, *values| yielder << block.call(*values) }
    end
    alias collect map

    def select(&block)
      Lazy.new(self) do |yielder, *values|
        value = values.size == 1 ? values[0] : values
        yielder << value if block.call(*values)
      end
    end
    alias filter select
    alias find_all select

    def reject(&block)
      Lazy.new(self) do |yielder, *values|
        value = values.size == 1 ? values[0] : values
        yielder << value unless block.call(*values)
      end
    end

    def filter_map(&block)
      Lazy.new(self) do |yielder, *values|
        result = block.call(*values)
        yielder << result if result
      end
    end

    def flat_map(&block)
      Lazy.new(self) do |yielder, *values|
        result = block.call(*values)
        if result.respond_to?(:force) && result.respond_to?(:each)
          result.each { |x| yielder << x }
        elsif result.is_a?(Array) || result.respond_to?(:to_ary)
          result.to_ary.each { |x| yielder << x }
        else
          yielder << result
        end
      end
    end
    alias collect_concat flat_map

    def grep(pattern, &block)
      Lazy.new(self) do |yielder, *values|
        value = values.size == 1 ? values[0] : values
        yielder << (block ? block.call(value) : value) if pattern === value
      end
    end

    def grep_v(pattern, &block)
      Lazy.new(self) do |yielder, *values|
        value = values.size == 1 ? values[0] : values
        yielder << (block ? block.call(value) : value) unless pattern === value
      end
    end

    def compact
      Lazy.new(self) do |yielder, *values|
        value = values.size == 1 ? values[0] : values
        yielder << value unless value.nil?
      end
    end

    def take(n)
      source = self
      Lazy.__from do |blk|
        if n > 0
          taken = 0
          source.each do |*values|
            blk.call(*values)
            taken += 1
            break if taken >= n
          end
        end
      end
    end

    def take_while(&block)
      source = self
      Lazy.__from do |blk|
        source.each do |*values|
          break unless block.call(*values)
          blk.call(*values)
        end
      end
    end

    def drop(n)
      source = self
      Lazy.__from do |blk|
        dropped = 0
        source.each do |*values|
          if dropped < n
            dropped += 1
          else
            blk.call(*values)
          end
        end
      end
    end

    def drop_while(&block)
      source = self
      Lazy.__from do |blk|
        dropping = true
        source.each do |*values|
          dropping = false if dropping && !block.call(*values)
          blk.call(*values) unless dropping
        end
      end
    end

    def with_index(offset = 0, &block)
      source = self
      Lazy.__from do |blk|
        index = offset
        source.each do |*values|
          value = values.size == 1 ? values[0] : values
          if block
            block.call(value, index)
            blk.call(value)
          else
            blk.call(value, index)
          end
          index += 1
        end
      end
    end
    alias each_with_index with_index

    def zip(*others)
      source = self
      Lazy.__from do |blk|
        enums = others.map { |other| other.respond_to?(:next) ? other : other.each }
        index = 0
        source.each do |*values|
          value = values.size == 1 ? values[0] : values
          row = [value]
          enums.each do |enum|
            item = nil
            if enum.is_a?(Array)
              item = enum[index]
            else
              begin
                item = enum.next
              rescue StopIteration
                item = nil
              end
            end
            row << item
          end
          index += 1
          blk.call(row)
        end
      end
    end

    def uniq(&block)
      source = self
      Lazy.__from do |blk|
        seen = {}
        source.each do |*values|
          value = values.size == 1 ? values[0] : values
          key = block ? block.call(value) : value
          unless seen.key?(key)
            seen[key] = true
            blk.call(value)
          end
        end
      end
    end
  end
end

module Enumerable
  def lazy
    Enumerator::Lazy.new(self) { |yielder, *values| yielder.yield(*values) }
  end
end
