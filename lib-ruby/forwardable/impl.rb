# :stopdoc:
# The part of forwardable that CRuby's implements with
# RubyVM::InstructionSequence, which topaz does not have. Forwardable's
# own forwardable.rb (CRuby's) runs unchanged on top.
module Forwardable
  OPERATORS = %w[+ - * / % ** == != < <= > >= <=> << >> & | ^ ~ ! [] []= =~ !~ === +@ -@].freeze

  # Whether "().#{method}" is a call of method, so that the delegator can be
  # defined as plain Ruby; otherwise it is defined with __send__.
  def self._valid_method?(method)
    method = method.to_s
    method.match?(/\A[A-Za-z_]\w*[?!]?\z/) || OPERATORS.include?(method)
  end

  def self._compile_method(src, file, line)
    eval(src, nil, file, line)
  end
end
