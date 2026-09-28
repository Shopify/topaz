# A stand-in for RubyGems, which topaz does not have: Gem::Version and
# Gem::Requirement, and Gem.loaded_specs for the gems on the load path
# (their directories are named name-version).
module Gem
  VERSION = "3.7.2"

  class LoadError < ::LoadError
    attr_accessor :name, :requirement
  end

  class MissingSpecError < LoadError; end

  class Version
    include Comparable

    PATTERN = /\A\s*([0-9]+(?>\.[0-9a-zA-Z]+)*(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?)?\s*\z/

    def self.correct?(version)
      !version.nil? && PATTERN.match?(version.to_s)
    end

    def self.create(input)
      input.is_a?(Version) ? input : (input.nil? ? nil : new(input))
    end

    def initialize(version)
      version = version.to_s.strip
      raise ArgumentError, "Malformed version number string #{version}" unless self.class.correct?(version)
      version = "0" if version.empty?
      @version = version.gsub("-", ".pre.")
    end

    def version
      @version.dup
    end
    alias to_s version

    def inspect
      "#<Gem::Version #{@version.inspect}>"
    end

    def segments
      @version.scan(/[0-9]+|[a-z]+/i).map { |s| s =~ /\A\d+\z/ ? s.to_i : s }
    end

    def canonical_segments
      segs = segments
      segs.pop while segs.size > 1 && segs.last == 0
      segs
    end

    def prerelease?
      @version.match?(/[a-zA-Z]/)
    end

    def release
      return self unless prerelease?
      segs = segments
      segs.pop while segs.any? { |s| s.is_a?(String) }
      self.class.new(segs.join("."))
    end

    def bump
      segs = segments
      segs.pop while segs.any? { |s| s.is_a?(String) }
      segs.pop if segs.size > 1
      segs[-1] = segs[-1].to_i + 1
      self.class.new(segs.join("."))
    end

    def approximate_recommendation
      segs = segments
      segs.pop while segs.any? { |s| s.is_a?(String) }
      segs.pop while segs.size > 2
      segs.push 0 while segs.size < 2
      "~> #{segs.join(".")}"
    end

    def <=>(other)
      other = Version.new(other) if other.is_a?(String) && Version.correct?(other)
      return nil unless other.is_a?(Version)
      mine = canonical_segments
      theirs = other.canonical_segments
      [mine.size, theirs.size].max.times do |i|
        a = mine[i] || 0
        b = theirs[i] || 0
        next if a == b
        return -1 if a.is_a?(String) && b.is_a?(Integer)
        return 1 if a.is_a?(Integer) && b.is_a?(String)
        return a <=> b
      end
      0
    end

    def eql?(other)
      other.is_a?(Version) && @version == other.version
    end

    def hash
      canonical_segments.hash
    end
  end

  class Requirement
    OPS = {
      "=" => ->(v, r) { v == r }, "!=" => ->(v, r) { v != r },
      ">" => ->(v, r) { v > r }, "<" => ->(v, r) { v < r },
      ">=" => ->(v, r) { v >= r }, "<=" => ->(v, r) { v <= r },
      "~>" => ->(v, r) { v >= r && v.release < r.bump },
    }.freeze

    def self.default
      new(">= 0")
    end

    def self.create(*inputs)
      inputs.first.is_a?(Requirement) ? inputs.first : new(*inputs)
    end

    attr_reader :requirements

    def initialize(*requirements)
      requirements = requirements.flatten.compact
      requirements = [">= 0"] if requirements.empty?
      @requirements = requirements.map do |r|
        if r.is_a?(Version)
          ["=", r]
        else
          op, version = r.to_s.strip.match(/\A(=|!=|>=|<=|>|<|~>)?\s*(.+)\z/).captures
          [op || "=", Version.new(version)]
        end
      end
    end

    def satisfied_by?(version)
      version = Version.create(version)
      @requirements.all? { |op, r| OPS.fetch(op).call(version, r) }
    end
    alias === satisfied_by?
    alias =~ satisfied_by?

    def to_s
      @requirements.map { |op, v| "#{op} #{v}" }.join(", ")
    end
  end

  class Specification
    attr_reader :name, :version, :full_gem_path

    def self.find_by_name(name, *requirements)
      Gem.loaded_specs[name] or raise MissingSpecError, "Could not find '#{name}'"
    end

    def self.each(&block)
      Gem.loaded_specs.values.each(&block)
    end

    def initialize(name, version, full_gem_path)
      @name = name
      @version = Version.new(version)
      @full_gem_path = full_gem_path
    end

    def gem_dir
      @full_gem_path
    end

    def require_paths
      ["lib"]
    end

    def full_name
      "#{@name}-#{@version}"
    end
  end

  # Marks methods as deprecated; the stand-in does not warn.
  module Deprecate
    def self.skip
      @skip ||= false
    end

    def self.skip=(value)
      @skip = value
    end

    def self.skip_during
      old = skip
      self.skip = true
      yield
    ensure
      self.skip = old
    end

    def deprecate(name, replacement, year, month)
      name
    end
    module_function :deprecate

    def rubygems_deprecate(name, replacement = :none)
      name
    end
    module_function :rubygems_deprecate

    def rubygems_deprecate_command(version = nil)
      nil
    end
    module_function :rubygems_deprecate_command
  end

  class Platform
    RUBY = "ruby"
    CURRENT = "current"

    attr_reader :cpu, :os, :version

    def self.local
      @local ||= new(RbConfig::CONFIG["arch"] || "x86_64-linux")
    end

    def initialize(name)
      @cpu, @os = name.to_s.split("-", 2)
      @version = nil
    end

    def to_s
      [@cpu, @os].compact.join("-")
    end

    def to_a
      [@cpu, @os, @version]
    end

    def ==(other)
      other.is_a?(Platform) && to_a == other.to_a
    end
  end

  def self.loaded_specs
    @loaded_specs ||= begin
      specs = {}
      $LOAD_PATH.each do |path|
        next unless (match = path.match(%r{/gems/([^/]+)-(\d[^/-]*(?:-[^/]+)?)/lib\z}))
        specs[match[1]] ||= Specification.new(match[1], match[2], File.dirname(path))
      end
      specs
    end
  end

  def self.ruby_version
    Version.new(RUBY_VERSION)
  end

  def self.rubygems_version
    Version.new(VERSION)
  end

  def self.win_platform?
    false
  end

  def self.java_platform?
    false
  end

  # The gem directory: where the gems on the load path were installed.
  def self.dir
    spec = loaded_specs.values.first
    ENV["GEM_HOME"] || (spec ? File.dirname(File.dirname(spec.full_gem_path)) : File.expand_path("~/.gem"))
  end

  def self.default_dir
    dir
  end

  def self.user_dir
    File.expand_path("~/.gem/topaz")
  end

  def self.path
    [dir]
  end

  def self.paths
    self
  end

  def self.home
    dir
  end

  def self.bindir(install_dir = dir)
    File.join(install_dir, "bin")
  end

  def self.suffixes
    ["", ".rb"]
  end
end

module Kernel
  private

  def gem(name, *requirements)
    true
  end
end
