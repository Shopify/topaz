# The C half of json's generator (json/ext/generator.so): json's own
# pure-Ruby generator, written for TruffleRuby, serves as it.
require "json/truffle_ruby/generator"

module JSON
  module Ext
    Generator = JSON::TruffleRuby::Generator
  end
end
