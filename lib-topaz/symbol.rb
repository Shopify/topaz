class Symbol
  # One lambda per symbol, as CRuby caches them: `recv.meth(*args)` for
  # the first yielded value. Hash#each and friends yield a [key, value]
  # pair as one argument, so the receiver is the pair.
  @__topaz_procs = {}

  class << self
    private

    def __topaz_proc_for(sym)
      @__topaz_procs[sym] ||= lambda do |recv, *args, &blk|
        recv.__send__(sym, *args, &blk)
      end
    end
  end

  def to_proc
    Symbol.__send__(:__topaz_proc_for, self)
  end

  def to_sym
    self
  end
  alias intern to_sym

  alias id2name to_s

  def succ
    self.to_s.succ.to_sym
  end
  alias next succ

  def capitalize
    self.to_s.capitalize.to_sym
  end

  # [], slice, =~, match and match? are in RPython (symbolobject.py), so
  # that they set the caller's $~.

  def swapcase
    self.to_s.swapcase.to_sym
  end

  def casecmp(other)
    other.instance_of?(Symbol) ? self.to_s.casecmp(other.to_s) : nil
  end
end

class Symbol
  # Ruby 2.7
  def start_with?(*prefixes)
    to_s.start_with?(*prefixes)
  end

  def end_with?(*suffixes)
    to_s.end_with?(*suffixes)
  end

  # Ruby 3.0
  def name
    to_s.freeze
  end
end
