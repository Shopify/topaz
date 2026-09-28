# The Ruby half of digest: algorithms load on first use (Digest::SHA256,
# Digest(:MD5)), and file and Base64 helpers. The core is digest.so,
# lib-ruby/ext/digest.rb in topaz.
require "digest.so"

module Digest
  VERSION = "3.2.1"
  REQUIRE_MUTEX = Thread::Mutex.new

  def self.const_missing(name)
    lib = case name
          when :SHA256, :SHA384, :SHA512 then "digest/sha2"
          else "digest/#{name.to_s.downcase}"
          end
    begin
      require lib
    rescue LoadError
      raise LoadError, "library not found for class Digest::#{name} -- #{lib}", caller(1)
    end
    raise NameError, "uninitialized constant Digest::#{name}", caller(1) unless const_defined?(name)
    const_get(name)
  end

  class ::Digest::Class
    def self.file(name, *args)
      new(*args).file(name)
    end

    def self.base64digest(string, *args)
      [digest(string, *args)].pack("m0")
    end
  end

  module Instance
    def file(name)
      File.open(name, "rb") do |f|
        buffer = +""
        update(buffer) while f.read(16384, buffer)
      end
      self
    end

    def base64digest(string = nil)
      [string ? digest(string) : digest].pack("m0")
    end

    def base64digest!
      [digest!].pack("m0")
    end
  end
end

def Digest(name)
  const = name.to_sym
  Digest::REQUIRE_MUTEX.synchronize { Digest.const_missing(const) }
rescue LoadError
  raise unless Digest.const_defined?(const)
  Digest.const_get(const)
end
