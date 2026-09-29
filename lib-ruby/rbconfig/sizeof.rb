# RbConfig::SIZEOF and RbConfig::LIMITS (a C extension in CRuby), from the
# platform's C types as FFI sees them.
require "rbconfig"
require "ffi"

module RbConfig
  sizes = {}
  {
    "char" => :char, "short" => :short, "int" => :int, "long" => :long,
    "long long" => :long_long, "void*" => :pointer, "float" => :float,
    "double" => :double, "size_t" => :size_t, "ssize_t" => :ssize_t,
    "off_t" => :off_t, "time_t" => :time_t, "pid_t" => :pid_t,
    "int8_t" => :int8, "int16_t" => :int16, "int32_t" => :int32, "int64_t" => :int64,
    "uint8_t" => :uint8, "uint16_t" => :uint16, "uint32_t" => :uint32, "uint64_t" => :uint64,
  }.each do |name, type|
    sizes[name] = FFI.find_type(type).size
  end
  pointer = sizes["void*"]
  %w[intptr_t uintptr_t ptrdiff_t].each { |name| sizes[name] = pointer }
  sizes["_Bool"] = 1
  SIZEOF = sizes.freeze

  limits = {}
  { "CHAR" => "char", "SHRT" => "short", "INT" => "int", "LONG" => "long", "LLONG" => "long long" }.each do |prefix, name|
    bits = sizes[name] * 8
    limits["#{prefix}_MAX"] = 2 ** (bits - 1) - 1
    limits["#{prefix}_MIN"] = -(2 ** (bits - 1))
    limits["U#{prefix}_MAX"] = 2 ** bits - 1
  end
  limits["SIZE_MAX"] = 2 ** (sizes["size_t"] * 8) - 1
  LIMITS = limits.freeze
end
