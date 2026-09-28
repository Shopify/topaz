# OpenSSL for topaz: the parts of the openssl library that pure-Ruby code
# (Rails' KeyGenerator, MessageEncryptor, MessageVerifier, ...) needs, on
# libcrypto through FFI. It stands in for both openssl.so and openssl.rb.
#
# Digests, HMAC, PBKDF2, HKDF, random bytes and symmetric ciphers work.
# Public keys, X.509 and TLS exist so that code referring to them loads,
# but using them raises NotImplementedError.
require "digest"
require "topaz/libcrypto"

module OpenSSL
  VERSION = "3.3.1"
  OPENSSL_VERSION = Topaz::LibCrypto.OpenSSL_version(0)
  OPENSSL_LIBRARY_VERSION = OPENSSL_VERSION
  OPENSSL_VERSION_NUMBER = Topaz::LibCrypto.OpenSSL_version_num
  OPENSSL_FIPS = false

  class OpenSSLError < StandardError; end

  def self.fips_mode
    false
  end

  def self.fips_mode=(value)
    raise OpenSSLError, "This version of OpenSSL does not support FIPS mode" if value
    value
  end

  def self.fixed_length_secure_compare(a, b)
    a = Topaz.convert_type(a, String, :to_str)
    b = Topaz.convert_type(b, String, :to_str)
    raise ArgumentError, "inputs must be of equal length" unless a.bytesize == b.bytesize
    return true if a.bytesize == 0
    lib = Topaz::LibCrypto
    lib.CRYPTO_memcmp(lib.buffer(a), lib.buffer(b), a.bytesize) == 0
  end

  def self.secure_compare(a, b)
    hashed_a = OpenSSL::Digest.digest("SHA256", a)
    hashed_b = OpenSSL::Digest.digest("SHA256", b)
    OpenSSL.fixed_length_secure_compare(hashed_a, hashed_b) && a == b
  end

  def self.__topaz_unsupported(what)
    raise NotImplementedError, "#{what} is not supported by topaz's OpenSSL"
  end

  class Digest < ::Digest::Class
    class DigestError < OpenSSLError; end

    NAMES = %w[MD4 MD5 RIPEMD160 SHA1 SHA224 SHA256 SHA384 SHA512
               SHA3-224 SHA3-256 SHA3-384 SHA3-512 BLAKE2b512 BLAKE2s256].freeze

    def self.digest(name, data)
      new(name).digest(data)
    end

    def self.hexdigest(name, data)
      new(name).hexdigest(data)
    end

    def self.base64digest(name, data)
      new(name).base64digest(data)
    end

    def self.digests
      NAMES.map(&:downcase)
    end

    def self.__topaz_md(digest)
      if digest.is_a?(OpenSSL::Digest)
        digest.__topaz_md
      else
        name = Topaz.convert_type(digest, String, :to_str)
        Topaz::LibCrypto.md(name) or raise RuntimeError, "Unsupported digest algorithm (#{name})."
      end
    end

    attr_reader :__topaz_md

    def initialize(name, data = nil)
      if name.is_a?(OpenSSL::Digest)
        @name = name.name
        @__topaz_md = name.__topaz_md
      else
        @name = Topaz.convert_type(name, String, :to_str)
        @__topaz_md = Digest.__topaz_md(@name)
      end
      @__topaz_data = "".b
      update(data) if data
    end

    def initialize_copy(other)
      super
      @__topaz_data = other.instance_variable_get(:@__topaz_data).dup
    end

    def name
      @name.upcase
    end

    def update(data)
      @__topaz_data << Topaz.convert_type(data, String, :to_str).b
      self
    end
    alias << update

    def reset
      @__topaz_data = "".b
      self
    end

    def digest_length
      Topaz::LibCrypto.EVP_MD_get_size(@__topaz_md)
    end

    def block_length
      Topaz::LibCrypto.EVP_MD_get_block_size(@__topaz_md)
    end

    private

    def finish
      Topaz::LibCrypto.digest(@__topaz_md, @__topaz_data)
    end
  end

  Digest::NAMES.each do |algorithm|
    klass = Class.new(Digest) do
      define_method(:initialize) { |data = nil| super(algorithm, data) }
    end
    klass.singleton_class.define_method(:digest) { |data| new.digest(data) }
    klass.singleton_class.define_method(:hexdigest) { |data| new.hexdigest(data) }
    klass.singleton_class.define_method(:base64digest) { |data| new.base64digest(data) }
    Digest.const_set(algorithm.tr("-", "_"), klass)
  end

  class HMACError < OpenSSLError; end

  class HMAC
    def self.digest(digest, key, data)
      Topaz::LibCrypto.hmac(Digest.__topaz_md(digest), key.to_s, data.to_s)
    end

    def self.hexdigest(digest, key, data)
      digest(digest, key, data).unpack1("H*")
    end

    def self.base64digest(digest, key, data)
      [digest(digest, key, data)].pack("m0")
    end

    def initialize(key, digest)
      @key = Topaz.convert_type(key, String, :to_str).b
      @md = Digest.__topaz_md(digest)
      @data = "".b
    end

    def initialize_copy(other)
      super
      @data = @data.dup
    end

    def update(data)
      @data << Topaz.convert_type(data, String, :to_str).b
      self
    end
    alias << update

    def reset
      @data = "".b
      self
    end

    def digest
      Topaz::LibCrypto.hmac(@md, @key, @data)
    end

    def hexdigest
      digest.unpack1("H*")
    end
    alias to_s hexdigest
    alias inspect hexdigest

    def base64digest
      [digest].pack("m0")
    end

    def ==(other)
      return false unless other.is_a?(HMAC)
      OpenSSL.fixed_length_secure_compare(digest, other.digest) rescue false
    end
  end

  module PKCS5
    class PKCS5Error < OpenSSLError; end

    def self.pbkdf2_hmac(pass, salt, iter, keylen, digest)
      Topaz::LibCrypto.pbkdf2_hmac(pass.to_s, salt.to_s, Integer(iter), Integer(keylen),
                                   Digest.__topaz_md(digest))
    end

    def self.pbkdf2_hmac_sha1(pass, salt, iter, keylen)
      pbkdf2_hmac(pass, salt, iter, keylen, "sha1")
    end
  end

  module KDF
    class KDFError < OpenSSLError; end

    def self.pbkdf2_hmac(pass, salt:, iterations:, length:, hash:)
      PKCS5.pbkdf2_hmac(pass, salt, iterations, length, hash)
    end

    # RFC 5869.
    def self.hkdf(ikm, salt:, info:, length:, hash:)
      md = Digest.__topaz_md(hash)
      size = Topaz::LibCrypto.EVP_MD_get_size(md)
      raise KDFError, "length must be at most #{255 * size}" if length > 255 * size
      prk = Topaz::LibCrypto.hmac(md, salt.to_s.b, ikm.to_s.b)
      okm = "".b
      block = "".b
      counter = 1
      while okm.bytesize < length
        block = Topaz::LibCrypto.hmac(md, prk, block + info.to_s.b + counter.chr)
        okm << block
        counter += 1
      end
      okm[0, length]
    end
  end

  module Random
    def self.random_bytes(length)
      Topaz::LibCrypto.random_bytes(Integer(length))
    end

    def self.seed(string)
      string
    end

    def self.random_add(string, entropy)
      self
    end

    def self.load_random_file(filename)
      true
    end

    def self.write_random_file(filename)
      true
    end

    def self.status?
      true
    end
  end

  class Cipher
    class CipherError < OpenSSLError; end
    class AuthTagError < CipherError; end

    # EVP_CTRL_AEAD_SET_IVLEN, _GET_TAG and _SET_TAG.
    SET_IVLEN = 0x9
    GET_TAG = 0x10
    SET_TAG = 0x11

    def self.ciphers
      %w[aes-128-cbc aes-192-cbc aes-256-cbc aes-128-ctr aes-192-ctr aes-256-ctr
         aes-128-ecb aes-192-ecb aes-256-ecb aes-128-gcm aes-192-gcm aes-256-gcm
         aes-128-cfb aes-256-cfb aes-128-ofb aes-256-ofb chacha20 chacha20-poly1305
         des-ede3-cbc]
    end

    attr_reader :name, :key_len, :iv_len, :block_size

    def initialize(name)
      name = Topaz.convert_type(name, String, :to_str)
      lib = Topaz::LibCrypto
      @evp = lib.EVP_get_cipherbyname(name)
      @evp = lib.EVP_get_cipherbyname(name.downcase) if @evp.null?
      raise RuntimeError, "unsupported cipher algorithm (#{name})" if @evp.null?
      @name = name.upcase
      @key_len = lib.EVP_CIPHER_get_key_length(@evp)
      @iv_len = lib.EVP_CIPHER_get_iv_length(@evp)
      @block_size = lib.EVP_CIPHER_get_block_size(@evp)
      @authenticated = name.downcase.match?(/gcm|ocb|poly1305/)
      @encrypt = 1
      @padding = 1
      @key = nil
      @iv = nil
      @auth_tag = nil
      @ctx = nil
    end

    def authenticated?
      @authenticated
    end

    def encrypt(*args)
      @encrypt = 1
      __topaz_free
      self
    end

    def decrypt(*args)
      @encrypt = 0
      __topaz_free
      self
    end

    def reset
      __topaz_free
      self
    end

    def key=(key)
      key = Topaz.convert_type(key, String, :to_str)
      raise ArgumentError, "key must be #{@key_len} bytes" unless key.bytesize == @key_len
      @key = key.b
      __topaz_free
    end

    def iv=(iv)
      iv = Topaz.convert_type(iv, String, :to_str)
      raise ArgumentError, "iv must be #{@iv_len} bytes" unless iv.bytesize == @iv_len
      @iv = iv.b
      __topaz_free
    end

    def key_len=(length)
      raise ArgumentError, "key length can't be changed for #{@name}" unless length == @key_len
    end

    def iv_len=(length)
      raise CipherError, "cipher does not support AEAD" unless @authenticated
      @iv_len = Integer(length)
    end

    def padding=(padding)
      @padding = padding ? (padding == 0 ? 0 : 1) : 0
      __topaz_free
    end

    def random_key
      self.key = Topaz::LibCrypto.random_bytes(@key_len)
      @key
    end

    def random_iv
      self.iv = Topaz::LibCrypto.random_bytes(@iv_len)
      @iv
    end

    def auth_data=(data)
      raise CipherError, "AEAD not supported by this cipher" unless @authenticated
      data = Topaz.convert_type(data, String, :to_str)
      __topaz_run_update(data, FFI::Pointer::NULL, "couldn't set additional authenticated data")
    end

    def auth_tag=(tag)
      raise CipherError, "authentication tag not supported by this cipher" unless @authenticated
      @auth_tag = Topaz.convert_type(tag, String, :to_str).b
    end

    def auth_tag(length = 16)
      raise CipherError, "authentication tag not supported by this cipher" unless @authenticated
      raise CipherError, "retrieving the authentication tag failed" unless @auth_tag
      @auth_tag[0, length]
    end

    def update(data, buffer = nil)
      data = Topaz.convert_type(data, String, :to_str)
      raise ArgumentError, "data must not be empty" if data.empty?
      out = FFI::MemoryPointer.new(:char, data.bytesize + @block_size + 1)
      result = __topaz_run_update(data, out, "EVP_CipherUpdate")
      buffer ? buffer.replace(result) : result
    end

    def <<(data)
      update(data)
      self
    end

    def final
      lib = Topaz::LibCrypto
      ctx = __topaz_ctx
      if @authenticated && @encrypt == 0 && @auth_tag
        if lib.EVP_CIPHER_CTX_ctrl(ctx, SET_TAG, @auth_tag.bytesize, lib.buffer(@auth_tag)) != 1
          raise CipherError, "unable to set AEAD tag"
        end
      end
      out = FFI::MemoryPointer.new(:char, @block_size + 16)
      length = FFI::MemoryPointer.new(:int, 1)
      ok = lib.EVP_CipherFinal_ex(ctx, out, length) == 1
      unless ok
        __topaz_free
        if @authenticated && @encrypt == 0
          nil while lib.ERR_get_error != 0
          raise AuthTagError, "AEAD authentication tag verification failed"
        end
        raise CipherError, lib.error_message("cipher final failed")
      end
      result = lib.bytes(out, length.get_int32(0))
      if @authenticated && @encrypt == 1
        tag = FFI::MemoryPointer.new(:char, 16)
        if lib.EVP_CIPHER_CTX_ctrl(ctx, GET_TAG, 16, tag) == 1
          @auth_tag = lib.bytes(tag, 16)
        end
      end
      __topaz_free
      result
    end

    def pkcs5_keyivgen(pass, salt = nil, iterations = 2048, digest = "MD5")
      OpenSSL.__topaz_unsupported("Cipher#pkcs5_keyivgen")
    end

    private

    def __topaz_ctx
      return @ctx if @ctx
      raise CipherError, "key not set" unless @key
      lib = Topaz::LibCrypto
      ctx = lib.EVP_CIPHER_CTX_new
      null = FFI::Pointer::NULL
      if lib.EVP_CipherInit_ex(ctx, @evp, null, null, null, @encrypt) != 1
        lib.EVP_CIPHER_CTX_free(ctx)
        raise CipherError, lib.error_message("EVP_CipherInit_ex")
      end
      lib.EVP_CIPHER_CTX_set_padding(ctx, @padding)
      if @authenticated && @iv_len != lib.EVP_CIPHER_get_iv_length(@evp)
        lib.EVP_CIPHER_CTX_ctrl(ctx, SET_IVLEN, @iv_len, null)
      end
      iv = @iv ? lib.buffer(@iv) : lib.buffer("\0".b * @iv_len)
      if lib.EVP_CipherInit_ex(ctx, null, null, lib.buffer(@key), iv, @encrypt) != 1
        lib.EVP_CIPHER_CTX_free(ctx)
        raise CipherError, lib.error_message("EVP_CipherInit_ex")
      end
      @ctx = ctx
    end

    def __topaz_run_update(data, out, what)
      lib = Topaz::LibCrypto
      length = FFI::MemoryPointer.new(:int, 1)
      if lib.EVP_CipherUpdate(__topaz_ctx, out, length, lib.buffer(data), data.bytesize) != 1
        raise CipherError, lib.error_message(what)
      end
      out.null? ? "".b : lib.bytes(out, length.get_int32(0))
    end

    # The context is freed as soon as it is finished with, since topaz
    # has no finalizers for it.
    def __topaz_free
      Topaz::LibCrypto.EVP_CIPHER_CTX_free(@ctx) if @ctx
      @ctx = nil
    end
  end

  %w[AES AES128 AES192 AES256].each do |family|
    klass = Class.new(Cipher) do
      define_method(:initialize) do |*args|
        name = family == "AES" ? "aes-#{args.join("-")}" : "aes-#{family[3..]}-#{args.join("-")}"
        super(name.downcase)
      end
    end
    Cipher.const_set(family, klass)
  end

  class BNError < OpenSSLError; end

  # Big numbers as Integers.
  class BN
    include Comparable

    def self.rand(bits, *)
      new(::Random.new.rand(2**bits))
    end

    def initialize(value, base = 10)
      @value = case value
               when BN then value.to_i
               when Integer then value
               when String
                 case base
                 when 0, 2 then value.b.unpack1("H*").to_i(16) * (base == 0 ? 1 : 1)
                 when 16 then value.to_i(16)
                 else Integer(value, base)
                 end
               else Integer(value)
               end
    end

    def to_i
      @value
    end
    alias to_int to_i

    def to_s(base = 10)
      case base
      when 2 then [@value.to_s(16).rjust((@value.to_s(16).size + 1) / 2 * 2, "0")].pack("H*")
      when 16 then @value.to_s(16).upcase
      else @value.to_s(base)
      end
    end

    def inspect
      "#<OpenSSL::BN #{@value}>"
    end

    %i[+ - * / % ** << >>].each do |op|
      define_method(op) { |other| BN.new(@value.__send__(op, other.to_i)) }
    end

    def <=>(other)
      @value <=> other.to_i
    end

    def ==(other)
      other.respond_to?(:to_i) && @value == other.to_i
    end
    alias eql? ==

    def hash
      @value.hash
    end

    def coerce(other)
      [BN.new(other), self]
    end

    def num_bits
      @value.bit_length
    end

    def num_bytes
      (num_bits + 7) / 8
    end

    def zero?
      @value == 0
    end

    def one?
      @value == 1
    end

    def odd?
      @value.odd?
    end

    def negative?
      @value < 0
    end
  end

  module PKey
    class PKeyError < OpenSSLError; end

    class PKey
      def initialize(*)
        OpenSSL.__topaz_unsupported(self.class.name)
      end
    end

    class RSA < PKey
      class RSAError < PKeyError; end
    end

    class DSA < PKey; end
    class DH < PKey; end

    class EC < PKey
      class Group
        def initialize(*)
          OpenSSL.__topaz_unsupported("OpenSSL::PKey::EC::Group")
        end
      end

      class Point
        def initialize(*)
          OpenSSL.__topaz_unsupported("OpenSSL::PKey::EC::Point")
        end
      end
    end

    def self.read(*)
      OpenSSL.__topaz_unsupported("OpenSSL::PKey.read")
    end

    def self.generate_key(*)
      OpenSSL.__topaz_unsupported("OpenSSL::PKey.generate_key")
    end
  end

  module X509
    DEFAULT_CERT_AREA = "/etc/ssl"
    DEFAULT_CERT_DIR = "/etc/ssl/certs"
    DEFAULT_CERT_FILE = "/etc/ssl/cert.pem"
    DEFAULT_CERT_DIR_ENV = "SSL_CERT_DIR"
    DEFAULT_CERT_FILE_ENV = "SSL_CERT_FILE"
    DEFAULT_PRIVATE_DIR = "/etc/ssl/private"
    V_OK = 0
    V_FLAG_CRL_CHECK = 0x4
    V_FLAG_CRL_CHECK_ALL = 0x8
    PURPOSE_SSL_CLIENT = 1
    PURPOSE_SSL_SERVER = 2

    class CertificateError < OpenSSLError; end
    class StoreError < OpenSSLError; end
    class NameError < OpenSSLError; end
    class ExtensionError < OpenSSLError; end
    class RequestError < OpenSSLError; end
    class CRLError < OpenSSLError; end

    %w[Certificate Name Extension ExtensionFactory Request CRL Revoked Attribute
       StoreContext].each do |name|
      const_set(name, Class.new do
        define_method(:initialize) { |*| OpenSSL.__topaz_unsupported("OpenSSL::X509::#{name}") }
      end)
    end

    # A store that can be configured but never verifies anything.
    class Store
      attr_accessor :flags, :purpose, :trust, :time, :verify_callback
      attr_reader :error, :error_string, :chain

      def initialize
        @error = V_OK
      end

      def set_default_paths
        nil
      end

      def add_file(file)
        self
      end

      def add_path(path)
        self
      end

      def add_cert(cert)
        self
      end

      def add_crl(crl)
        self
      end

      def verify(*)
        OpenSSL.__topaz_unsupported("OpenSSL::X509::Store#verify")
      end
    end
  end

  module SSL
    VERIFY_NONE = 0
    VERIFY_PEER = 1
    VERIFY_FAIL_IF_NO_PEER_CERT = 2
    VERIFY_CLIENT_ONCE = 4
    OP_ALL = 0x80000850
    OP_NO_COMPRESSION = 0x20000
    OP_NO_SSLv2 = 0
    OP_NO_SSLv3 = 0x2000000
    OP_NO_TLSv1 = 0x4000000
    OP_NO_TLSv1_1 = 0x10000000
    OP_NO_TLSv1_2 = 0x8000000
    OP_NO_TLSv1_3 = 0x20000000
    OP_NO_TICKET = 0x4000
    OP_CIPHER_SERVER_PREFERENCE = 0x400000
    SSL2_VERSION = 0x0002
    SSL3_VERSION = 0x0300
    TLS1_VERSION = 0x0301
    TLS1_1_VERSION = 0x0302
    TLS1_2_VERSION = 0x0303
    TLS1_3_VERSION = 0x0304

    class SSLError < OpenSSLError; end
    class SSLErrorWaitReadable < SSLError; end
    class SSLErrorWaitWritable < SSLError; end

    class SSLContext
      DEFAULT_PARAMS = {
        min_version: TLS1_VERSION,
        verify_mode: VERIFY_PEER,
        verify_hostname: true,
        options: OP_ALL | OP_NO_COMPRESSION,
      }.freeze
      DEFAULT_CERT_STORE = X509::Store.new.tap(&:set_default_paths)
      METHODS = %i[TLS TLS_client TLS_server SSLv23 SSLv23_client SSLv23_server].freeze

      attr_accessor :cert, :key, :client_ca, :ca_file, :ca_path, :timeout, :verify_mode,
                    :verify_depth, :verify_callback, :verify_hostname, :cert_store,
                    :extra_chain_cert, :client_cert_cb, :session_id_context, :options,
                    :servername_cb, :alpn_protocols, :alpn_select_cb, :npn_protocols,
                    :npn_select_cb, :renegotiation_cb, :ciphers, :ciphersuites,
                    :min_version, :max_version, :security_level, :ssl_version,
                    :tmp_dh_callback, :ecdh_curves, :keylog_cb, :session_cache_mode,
                    :session_cache_size

      def initialize(version = nil)
        @options = DEFAULT_PARAMS[:options]
        @verify_mode = VERIFY_NONE
        @verify_hostname = false
      end

      def set_params(params = {})
        DEFAULT_PARAMS.merge(params).each { |name, value| __send__("#{name}=", value) }
        @cert_store ||= DEFAULT_CERT_STORE
        params
      end

      def setup
        true
      end
      alias freeze setup

      def add_certificate(*)
        self
      end
    end

    class SSLSocket
      def initialize(*)
        OpenSSL.__topaz_unsupported("OpenSSL::SSL::SSLSocket")
      end
    end

    class SSLServer
      def initialize(*)
        OpenSSL.__topaz_unsupported("OpenSSL::SSL::SSLServer")
      end
    end

    class Session
      class SessionError < OpenSSLError; end
    end

    def self.verify_certificate_identity(cert, hostname)
      OpenSSL.__topaz_unsupported("OpenSSL::SSL.verify_certificate_identity")
    end
  end

  module ASN1
    class ASN1Error < OpenSSLError; end
  end

  class ConfigError < OpenSSLError; end

  class Config
    DEFAULT_CONFIG_FILE = "/etc/ssl/openssl.cnf"
  end
end

class Integer
  def to_bn
    OpenSSL::BN.new(self)
  end
end
