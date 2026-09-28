# The C half of digest (digest.so): Digest::Instance, Digest::Class and
# Digest::Base. The algorithms (digest/md5.so, digest/sha2.so, ...) are
# Digest::Base subclasses computed by libcrypto; digest.rb runs on top.
module Digest
  def self.hexencode(string)
    Topaz.convert_type(string, String, :to_str).unpack1("H*")
  end

  module Instance
    def update(string)
      raise RuntimeError, "#{self.class}#update not implemented"
    end

    def <<(string)
      update(string)
    end

    def reset
      raise RuntimeError, "#{self.class}#reset not implemented"
    end

    def new
      copy = clone
      copy.reset
      copy
    end

    def digest(string = nil)
      if string.nil?
        clone.__send__(:finish)
      else
        reset
        update(string)
        value = finish
        reset
        value
      end
    end

    def digest!
      value = finish
      reset
      value
    end

    def hexdigest(string = nil)
      Digest.hexencode(digest(string))
    end

    def hexdigest!
      Digest.hexencode(digest!)
    end

    def to_s
      hexdigest
    end

    def inspect
      "#<#{self.class.name}: #{hexdigest}>"
    end

    def ==(other)
      if other.is_a?(Digest::Instance)
        digest == other.digest
      else
        return false unless other.respond_to?(:to_str)
        other = other.to_str
        # A string compares with the digest or with its hex form.
        other.bytesize == digest_length ? digest == other : hexdigest == other
      end
    end

    def digest_length
      digest.bytesize
    end

    def block_length
      raise RuntimeError, "#{self.class}#block_length not implemented"
    end

    def length
      digest_length
    end

    def size
      digest_length
    end

    private

    def finish
      raise RuntimeError, "#{self.class}#finish not implemented"
    end
  end

  class Class
    include Instance

    def self.digest(string, *args)
      new(*args).digest(string)
    end

    def self.hexdigest(string, *args)
      Digest.hexencode(digest(string, *args))
    end

    def initialize
    end
  end

  # An algorithm libcrypto computes; subclasses name it with
  # __topaz_algorithm. The data is buffered and hashed in one go.
  class Base < Class
    def self.__topaz_md
      @__topaz_md ||= begin
        require "topaz/libcrypto"
        name = __topaz_algorithm
        Topaz::LibCrypto.md(name) or
          raise NotImplementedError, "#{self.name}: libcrypto has no #{name}"
      end
    end

    def self.__topaz_algorithm
      raise NotImplementedError, "Digest::Base is an abstract class"
    end

    def initialize
      raise NotImplementedError, "Digest::Base is an abstract class" if self.class == Base
      self.class.__topaz_md
      @__topaz_data = "".b
    end

    def initialize_copy(other)
      super
      @__topaz_data = other.instance_variable_get(:@__topaz_data).dup
    end

    def update(string)
      @__topaz_data << Topaz.convert_type(string, String, :to_str).b
      self
    end

    def <<(string)
      update(string)
    end

    def reset
      @__topaz_data = "".b
      self
    end

    def digest_length
      Topaz::LibCrypto.EVP_MD_get_size(self.class.__topaz_md)
    end

    def block_length
      Topaz::LibCrypto.EVP_MD_get_block_size(self.class.__topaz_md)
    end

    private

    def finish
      Topaz::LibCrypto.digest(self.class.__topaz_md, @__topaz_data)
    end
  end
end
