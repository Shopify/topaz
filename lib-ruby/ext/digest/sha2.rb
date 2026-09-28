# digest/sha2.so: Digest::SHA256, SHA384 and SHA512, computed by libcrypto.
require "digest"

module Digest
  class SHA256 < Base
    def self.__topaz_algorithm
      "sha256"
    end
  end

  class SHA384 < Base
    def self.__topaz_algorithm
      "sha384"
    end
  end

  class SHA512 < Base
    def self.__topaz_algorithm
      "sha512"
    end
  end
end
