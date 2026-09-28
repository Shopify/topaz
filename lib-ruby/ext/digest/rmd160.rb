# digest/rmd160.so: Digest::RMD160, computed by libcrypto.
require "digest"

module Digest
  class RMD160 < Base
    def self.__topaz_algorithm
      "ripemd160"
    end
  end
end
