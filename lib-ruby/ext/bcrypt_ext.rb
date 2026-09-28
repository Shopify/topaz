# The C half of bcrypt (bcrypt_ext.so): BCrypt::Engine.__bc_salt and
# __bc_crypt, on libxcrypt's crypt_gensalt_ra and crypt_ra (the same
# Openwall interface the gem bundles) through FFI. Found by name, or
# through TOPAZ_LIBCRYPT.
require "ffi"

module BCrypt
  module LibCrypt
    extend FFI::Library

    candidates = [ENV["TOPAZ_LIBCRYPT"], "libcrypt.so.2", "libcrypt.so.1", "libcrypt.so", "crypt"].compact
    loaded = false
    candidates.each do |name|
      begin
        ffi_lib name
        loaded = true
        break
      rescue LoadError
      end
    end
    raise LoadError, "cannot load libcrypt (set TOPAZ_LIBCRYPT to its path)" unless loaded

    attach_function :crypt_gensalt_ra, [:string, :ulong, :pointer, :int], :pointer
    attach_function :crypt_ra, [:string, :string, :pointer, :pointer], :pointer
    attach_function :free, [:pointer], :void

    def self.c_string(value)
      value = Topaz.convert_type(value, String, :to_str)
      raise ArgumentError, "string contains null byte" if value.include?("\0")
      value
    end
  end

  class Engine
    def self.__bc_salt(prefix, count, input)
      prefix = LibCrypt.c_string(prefix)
      if input.nil?
        pointer = FFI::Pointer::NULL
        size = 0
      else
        input = Topaz.convert_type(input, String, :to_str)
        pointer = FFI::MemoryPointer.new(:char, input.bytesize + 1)
        pointer.put_bytes(0, input, 0, input.bytesize) if input.bytesize > 0
        size = input.bytesize
      end
      salt = LibCrypt.crypt_gensalt_ra(prefix, Integer(count), pointer, size)
      return nil if salt.null?
      result = salt.get_string(0)
      LibCrypt.free(salt)
      result
    end

    def self.__bc_crypt(key, setting)
      return nil if key.nil? || setting.nil?
      key = LibCrypt.c_string(key)
      setting = LibCrypt.c_string(setting)
      data = FFI::MemoryPointer.new(:pointer, 1)
      size = FFI::MemoryPointer.new(:int, 1)
      value = LibCrypt.crypt_ra(key, setting, data, size)
      buffer = data.get_pointer(0)
      return nil if value.null? || buffer.null?
      result = value.get_string(0)
      LibCrypt.free(buffer)
      result
    end
  end
end
