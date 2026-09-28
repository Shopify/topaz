# A stand-in for Bundler: CRuby's bundler installed the gems, and run.rb
# put their load paths on $LOAD_PATH already. Bundler.require replays the
# requires CRuby's Bundler.require would do (bundler_requires.txt).
module Bundler
  REQUIRES = File.expand_path("../bundler_requires.txt", __dir__)

  def self.setup(*groups)
    self
  end

  def self.require(*groups)
    File.read(REQUIRES).split("\n").each do |name|
      Kernel.require(name)
    end
  end

  def self.root
    Pathname.new(Dir.pwd)
  end
end
