# digest/sha1.so: Digest::SHA1, computed by libcrypto.
require "digest"

module Digest
  class SHA1 < Base
    def self.__topaz_algorithm
      "sha1"
    end
  end
end
