# A stand-in for Bundler: CRuby's bundler installed the gems, and run.rb
# put their load paths on $LOAD_PATH already. Bundler.require replays the
# requires CRuby's Bundler.require would do (bundler_requires.txt).
module Bundler
  REQUIRES = File.expand_path("../bundler_requires.txt", __dir__)

  def self.setup(*groups)
    self
  end

  # As Bundler does, a gem without a file of its own name is skipped, and
  # "a-b" is tried as "a/b".
  def self.require(*groups)
    File.read(REQUIRES).split("\n").each do |name|
      begin
        Kernel.require(name)
      rescue LoadError => e
        raise unless e.path == name
        next unless name.include?("-")
        begin
          Kernel.require(name.tr("-", "/"))
        rescue LoadError => e
          raise unless e.path == name.tr("-", "/")
        end
      end
    end
  end

  def self.root
    Pathname.new(Dir.pwd)
  end
end
