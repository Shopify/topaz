class Method
  def to_proc
    Proc.new { |*args, &blk| self.call(*args, &blk) }
  end
end

class Method
  # Ruby 2.6
  def >>(g)
    to_proc >> g
  end

  def <<(g)
    to_proc << g
  end

  def curry(arity = nil)
    to_proc.curry(arity)
  end
end
