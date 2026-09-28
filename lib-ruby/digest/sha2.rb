# Digest::SHA2, a SHA-2 digest of 256, 384 or 512 bits.
require "digest"
require "digest/sha2.so"

module Digest
  class SHA2 < Digest::Class
    def initialize(bitlen = 256)
      @sha2 = case bitlen
              when 256 then Digest::SHA256.new
              when 384 then Digest::SHA384.new
              when 512 then Digest::SHA512.new
              else raise ArgumentError, "unsupported bit length: %s" % bitlen.inspect
              end
      @bitlen = bitlen
    end

    def initialize_copy(other)
      @sha2 = other.instance_eval { @sha2.clone }
      @bitlen = other.instance_eval { @bitlen }
    end

    def reset
      @sha2.reset
      self
    end

    def update(string)
      @sha2.update(string)
      self
    end
    alias << update

    def block_length
      @sha2.block_length
    end

    def digest_length
      @sha2.digest_length
    end

    def inspect
      "#<%s:%d %s>" % [self.class.name, @bitlen, hexdigest]
    end

    private

    def finish
      @sha2.digest!
    end
  end
end
