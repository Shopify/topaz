# OpenSSL's libcrypto through FFI, shared by topaz's digest and openssl.
#
# Hashes and HMACs are computed one-shot over data buffered in Ruby, so no
# native state has to be freed or copied; ciphers keep an EVP context.
require "ffi"

module Topaz
  module LibCrypto
    extend FFI::Library

    candidates = [ENV["TOPAZ_LIBCRYPTO"], "libcrypto.so.3", "libcrypto.so", "crypto"].compact
    loaded = false
    candidates.each do |name|
      begin
        ffi_lib name
        loaded = true
        break
      rescue LoadError
      end
    end
    raise LoadError, "cannot load libcrypto (set TOPAZ_LIBCRYPTO to its path)" unless loaded

    # OpenSSL 3 renamed the accessors (the old names became macros).
    def self.attach_either(name, names, args, ret)
      names.each do |c_name|
        begin
          attach_function name, c_name, args, ret
          return
        rescue LoadError
        end
      end
      raise LoadError, "libcrypto has none of #{names.join(", ")}"
    end

    attach_function :OpenSSL_version_num, [], :ulong
    attach_function :OpenSSL_version, [:int], :string
    attach_function :RAND_bytes, [:pointer, :int], :int
    attach_function :CRYPTO_memcmp, [:pointer, :pointer, :size_t], :int
    attach_function :ERR_get_error, [], :ulong
    attach_function :ERR_error_string_n, [:ulong, :pointer, :size_t], :void

    attach_function :EVP_get_digestbyname, [:string], :pointer
    attach_either :EVP_MD_get_size, %w[EVP_MD_get_size EVP_MD_size], [:pointer], :int
    attach_either :EVP_MD_get_block_size, %w[EVP_MD_get_block_size EVP_MD_block_size],
                  [:pointer], :int
    attach_function :EVP_Digest, [:pointer, :size_t, :pointer, :pointer, :pointer, :pointer], :int
    attach_function :HMAC, [:pointer, :pointer, :int, :pointer, :size_t, :pointer, :pointer],
                    :pointer
    attach_function :PKCS5_PBKDF2_HMAC,
                    [:pointer, :int, :pointer, :int, :int, :pointer, :int, :pointer], :int

    attach_function :EVP_get_cipherbyname, [:string], :pointer
    attach_either :EVP_CIPHER_get_key_length, %w[EVP_CIPHER_get_key_length EVP_CIPHER_key_length],
                  [:pointer], :int
    attach_either :EVP_CIPHER_get_iv_length, %w[EVP_CIPHER_get_iv_length EVP_CIPHER_iv_length],
                  [:pointer], :int
    attach_either :EVP_CIPHER_get_block_size, %w[EVP_CIPHER_get_block_size EVP_CIPHER_block_size],
                  [:pointer], :int
    attach_function :EVP_CIPHER_CTX_new, [], :pointer
    attach_function :EVP_CIPHER_CTX_free, [:pointer], :void
    attach_function :EVP_CIPHER_CTX_reset, [:pointer], :int
    attach_function :EVP_CipherInit_ex, [:pointer, :pointer, :pointer, :pointer, :pointer, :int],
                    :int
    attach_function :EVP_CipherUpdate, [:pointer, :pointer, :pointer, :pointer, :int], :int
    attach_function :EVP_CipherFinal_ex, [:pointer, :pointer, :pointer], :int
    attach_function :EVP_CIPHER_CTX_ctrl, [:pointer, :int, :int, :pointer], :int
    attach_function :EVP_CIPHER_CTX_set_padding, [:pointer, :int], :int
    attach_function :EVP_CIPHER_CTX_set_key_length, [:pointer, :int], :int

    EVP_MAX_MD_SIZE = 64

    # A copy of str's bytes in native memory (never NULL, even when empty).
    def self.buffer(str)
      str = str.to_s
      memory = FFI::MemoryPointer.new(:char, str.bytesize + 1)
      memory.put_bytes(0, str, 0, str.bytesize) if str.bytesize > 0
      memory
    end

    def self.bytes(pointer, length)
      length == 0 ? "".b : pointer.get_bytes(0, length).b
    end

    # The EVP_MD for a digest name ("SHA256", "sha-256", "md5"), or nil.
    def self.md(name)
      name = name.to_s
      md = EVP_get_digestbyname(name)
      md = EVP_get_digestbyname(name.downcase) if md.null?
      md = EVP_get_digestbyname(name.downcase.delete("-")) if md.null?
      md.null? ? nil : md
    end

    def self.digest(md, data)
      out = FFI::MemoryPointer.new(:char, EVP_MAX_MD_SIZE)
      length = FFI::MemoryPointer.new(:uint, 1)
      if EVP_Digest(buffer(data), data.bytesize, out, length, md, FFI::Pointer::NULL) != 1
        raise error_message("EVP_Digest")
      end
      bytes(out, length.get_uint32(0))
    end

    def self.hmac(md, key, data)
      out = FFI::MemoryPointer.new(:char, EVP_MAX_MD_SIZE)
      length = FFI::MemoryPointer.new(:uint, 1)
      if HMAC(md, buffer(key), key.bytesize, buffer(data), data.bytesize, out, length).null?
        raise error_message("HMAC")
      end
      bytes(out, length.get_uint32(0))
    end

    def self.pbkdf2_hmac(pass, salt, iterations, length, md)
      out = FFI::MemoryPointer.new(:char, length + 1)
      if PKCS5_PBKDF2_HMAC(buffer(pass), pass.bytesize, buffer(salt), salt.bytesize,
                           iterations, md, length, out) != 1
        raise error_message("PKCS5_PBKDF2_HMAC")
      end
      bytes(out, length)
    end

    def self.random_bytes(length)
      out = FFI::MemoryPointer.new(:char, length + 1)
      raise error_message("RAND_bytes") if RAND_bytes(out, length) != 1
      bytes(out, length)
    end

    # The oldest queued OpenSSL error, as OpenSSL's messages are shown.
    def self.error_message(function)
      code = ERR_get_error()
      return function if code == 0
      text = FFI::MemoryPointer.new(:char, 256)
      ERR_error_string_n(code, text, 256)
      nil while ERR_get_error() != 0
      reason = text.get_string(0).split(":", 5).last
      "#{function}: #{reason}"
    end
  end
end
