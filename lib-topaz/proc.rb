class Proc
  # Ruby 2.6: function composition.
  def >>(g)
    f = self
    lambda { |*args, &block| g.call(f.call(*args, &block)) }
  end

  def <<(g)
    f = self
    lambda { |*args, &block| f.call(g.call(*args, &block)) }
  end

  def curry(arity = nil)
    if arity.nil?
      arity = self.arity < 0 ? -self.arity - 1 : self.arity
    elsif lambda? && self.arity >= 0 && arity != self.arity
      raise ArgumentError.new("wrong number of arguments (given #{arity}, expected #{self.arity})")
    end
    Topaz.curry(self, arity, [])
  end
end

module Topaz
  def self.curry(proc, arity, args)
    lambda do |*more|
      all = args + more
      if all.size >= arity
        proc.call(*all)
      else
        Topaz.curry(proc, arity, all)
      end
    end
  end
end
