module Errno
  # One class per errno; aliases (EWOULDBLOCK for EAGAIN) name the same
  # class. (An Array: this runs before Integer#eql? exists for a Hash.)
  by_code = []
  Topaz::ERRNO_LIST.each do |name, code, text|
    klass = by_code[code]
    unless klass
      klass = Class.new(SystemCallError)
      klass.const_set(:Errno, code)
      klass.const_set(:Strerror, text)
      klass.class_eval do
        def initialize(msg = nil)
          text = self.class::Strerror
          super(msg.nil? ? text : "#{text} - #{msg}", self.class::Errno)
        end
      end
      klass.private_constant(:Strerror)
      by_code[code] = klass
    end
    const_set(name, klass)
  end
end
