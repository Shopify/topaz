# A small Fiddle on top of FFI: dlopen, symbol lookup and calling a C
# function through Fiddle::Function. Closures, Fiddle::Pointer arithmetic
# and structs are not supported.
require "ffi"

module Fiddle
  class Error < StandardError; end
  class DLError < Error; end

  TYPE_VOID = 0
  TYPE_VOIDP = 1
  TYPE_CHAR = 2
  TYPE_SHORT = 3
  TYPE_INT = 4
  TYPE_LONG = 5
  TYPE_LONG_LONG = 6
  TYPE_FLOAT = 7
  TYPE_DOUBLE = 8
  TYPE_VARIADIC = 9
  TYPE_CONST_STRING = 10
  TYPE_BOOL = 11
  TYPE_INT8_T = TYPE_CHAR
  TYPE_INT16_T = TYPE_SHORT
  TYPE_INT32_T = TYPE_INT
  TYPE_INT64_T = TYPE_LONG
  TYPE_UINT8_T = -TYPE_CHAR
  TYPE_UINT16_T = -TYPE_SHORT
  TYPE_UINT32_T = -TYPE_INT
  TYPE_UINT64_T = -TYPE_LONG
  TYPE_SIZE_T = -TYPE_LONG
  TYPE_SSIZE_T = TYPE_LONG
  TYPE_PTRDIFF_T = TYPE_LONG
  TYPE_INTPTR_T = TYPE_LONG
  TYPE_UINTPTR_T = -TYPE_LONG

  SIZEOF_VOIDP = FFI.find_type(:pointer).size
  SIZEOF_CHAR = 1
  SIZEOF_UCHAR = 1
  SIZEOF_BOOL = 1
  SIZEOF_SHORT = FFI.find_type(:short).size
  SIZEOF_USHORT = SIZEOF_SHORT
  SIZEOF_INT = FFI.find_type(:int).size
  SIZEOF_UINT = SIZEOF_INT
  SIZEOF_LONG = FFI.find_type(:long).size
  SIZEOF_ULONG = SIZEOF_LONG
  SIZEOF_LONG_LONG = FFI.find_type(:long_long).size
  SIZEOF_ULONG_LONG = SIZEOF_LONG_LONG
  SIZEOF_FLOAT = 4
  SIZEOF_DOUBLE = 8
  SIZEOF_SIZE_T = FFI.find_type(:size_t).size
  SIZEOF_SSIZE_T = SIZEOF_SIZE_T
  SIZEOF_PTRDIFF_T = SIZEOF_VOIDP
  SIZEOF_INTPTR_T = SIZEOF_VOIDP
  SIZEOF_UINTPTR_T = SIZEOF_VOIDP
  SIZEOF_CONST_STRING = SIZEOF_VOIDP
  SIZEOF_INT8_T = 1
  SIZEOF_INT16_T = 2
  SIZEOF_INT32_T = 4
  SIZEOF_INT64_T = 8
  SIZEOF_UINT8_T = 1
  SIZEOF_UINT16_T = 2
  SIZEOF_UINT32_T = 4
  SIZEOF_UINT64_T = 8

  RTLD_LAZY = FFI::DynamicLibrary::RTLD_LAZY
  RTLD_GLOBAL = FFI::DynamicLibrary::RTLD_GLOBAL
  RTLD_NOW = FFI::DynamicLibrary::RTLD_NOW

  # FFI's name for each Fiddle type; negative types are unsigned.
  FFI_TYPES = {
    TYPE_VOID => :void, TYPE_VOIDP => :pointer, TYPE_CHAR => :char,
    TYPE_SHORT => :short, TYPE_INT => :int, TYPE_LONG => :long,
    TYPE_LONG_LONG => :long_long, TYPE_FLOAT => :float, TYPE_DOUBLE => :double,
    TYPE_CONST_STRING => :string, TYPE_BOOL => :bool,
    -TYPE_CHAR => :uchar, -TYPE_SHORT => :ushort, -TYPE_INT => :uint,
    -TYPE_LONG => :ulong, -TYPE_LONG_LONG => :ulong_long,
  }

  def self.ffi_type(type)
    name = FFI_TYPES[type] or raise DLError, "unknown type: #{type}"
    FFI.find_type(name)
  end

  # A native address. Fiddle::Pointer[string] and arithmetic are not
  # supported.
  class Pointer
    def initialize(address, size = 0, free = nil)
      @address = address.to_i
      @size = size
    end

    attr_reader :size

    def to_i
      @address
    end
    alias to_int to_i

    def null?
      @address == 0
    end

    def ==(other)
      other.respond_to?(:to_i) && other.to_i == @address
    end

    def inspect
      "#<#{self.class.name}:0x#{@address.to_s(16)}>"
    end
  end

  NULL = Pointer.new(0)

  # FFI::Function wants the library symbol an address came from.
  SYMBOLS = {}

  class Handle
    NEXT = nil
    DEFAULT = nil

    def initialize(library = nil, flags = RTLD_LAZY | RTLD_GLOBAL)
      @library = FFI::DynamicLibrary.open(library, flags)
    rescue LoadError => e
      raise DLError, e.message
    end

    def sym(name)
      symbol = @library.find_function(name.to_s) || @library.find_variable(name.to_s)
      raise DLError, "unknown symbol \"#{name}\"" unless symbol
      Fiddle::SYMBOLS[symbol.address] = symbol
      symbol.address
    end
    alias [] sym

    def close
      0
    end
  end

  def self.dlopen(library)
    Handle.new(library)
  end

  class Function
    DEFAULT = :default
    STDCALL = :stdcall

    attr_reader :ptr, :name, :abi

    def initialize(ptr, args, ret_type, abi = DEFAULT, name: nil, need_gvl: false)
      @ptr = ptr.to_i
      @args = args
      @ret_type = ret_type
      @abi = abi
      @name = name
      symbol = SYMBOLS[@ptr] or raise DLError, "no function known at 0x#{@ptr.to_s(16)}"
      @function = FFI::Function.new(Fiddle.ffi_type(ret_type), args.map { |t| Fiddle.ffi_type(t) }, symbol)
    end

    def to_i
      @ptr
    end

    # A String passed for a pointer is copied into native memory, and what
    # the function wrote there is copied back.
    def call(*args)
      raise ArgumentError, "wrong number of arguments (given #{args.size}, expected #{@args.size})" if args.size != @args.size
      buffers = []
      native = args.each_with_index.map do |arg, i|
        if @args[i] == TYPE_VOIDP
          case arg
          when String
            memory = FFI::MemoryPointer.new(:char, arg.bytesize + 1)
            memory.put_bytes(0, arg)
            buffers << [arg, memory]
            memory
          when nil then FFI::Pointer.new(0)
          when Pointer, Integer then FFI::Pointer.new(arg.to_i)
          else arg
          end
        else
          arg
        end
      end
      result = @function.call(*native)
      buffers.each do |string, memory|
        string.replace(memory.get_bytes(0, string.bytesize).force_encoding(string.encoding))
      end
      @ret_type == TYPE_VOIDP ? Pointer.new(result.address) : result
    end
  end
end
