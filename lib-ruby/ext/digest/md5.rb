# digest/md5.so: Digest::MD5, computed by libcrypto.
require "digest"

module Digest
  class MD5 < Base
    def self.__topaz_algorithm
      "md5"
    end
  end
end
