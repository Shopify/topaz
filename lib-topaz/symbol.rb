class Symbol
  # One lambda per symbol, as CRuby caches them: `recv.meth(*args)` for
  # the first yielded value. Hash#each and friends yield a [key, value]
  # pair as one argument, so the receiver is the pair. Symbol#to_proc
  # (RPython) keeps the lambda on the symbol object.
  class << self
    private

    OPERATORS = %w[+ - * / % ** == != < <= > >= <=> << >> & | ^ ~ ! =~ !~ -@ +@ ===].freeze

    # The lambda is compiled with the method name as a literal, so the
    # call is an ordinary call site (inline cache per site) rather than a
    # __send__ with a variable name. Keywords are not forwarded, as before.
    def __topaz_build_proc(sym)
      name = sym.to_s
      if name =~ /\A[A-Za-z_][A-Za-z0-9_]*[?!]?\z/ || OPERATORS.include?(name)
        eval("lambda { |recv, *args, &blk| recv.#{name}(*args, &blk) }")
      else
        lambda { |recv, *args, &blk| recv.__send__(sym, *args, &blk) }
      end
    end
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
