# A stand-in for Bundler, which topaz does not have. CRuby's Bundler (the
# `bundle` on PATH) installs the gems and resolves the Gemfile; so a
# benchmark that does `bundle install` and then Bundler.setup works as on
# CRuby. Bundler.setup asks `bundle exec ruby` for the resolved bundle
# (topaz/bundler_resolve.rb) and puts the gems' require paths before, and
# CRuby's pure-Ruby standard library after, topaz's own library on the
# load path. Bundler.require replays the requires CRuby's Bundler.require
# would do.
#
# Topaz cannot load C extensions; lib-ruby/ext has Ruby replacements for
# some of them.
require "rubygems"

module Bundler
  class BundlerError < StandardError; end
  class GemfileNotFound < BundlerError; end
  class GemRequireError < BundlerError; end

  RESOLVE_SCRIPT = File.expand_path("topaz/bundler_resolve.rb", __dir__)

  Dependency = Struct.new(:name, :groups, :explicit_require, :files)

  @setup = false
  @dependencies = []

  class << self
    attr_reader :dependencies

    def setup(*groups)
      return self if @setup
      resolve
      @setup = true
      self
    end

    # Like Bundler, requires the autorequire files of the given groups'
    # dependencies (the default group when none is given). A gem without a
    # file of its own name is skipped, and "a-b" is tried as "a/b"; a file
    # named explicitly in the Gemfile must load.
    def require(*groups)
      setup
      groups = [:default] if groups.empty?
      groups = groups.map(&:to_s)
      @dependencies.each do |dep|
        next if (dep.groups & groups).empty?
        dep.files.each do |file|
          begin
            Kernel.require(file)
          rescue LoadError => e
            raise if dep.explicit_require || e.path != file
            next unless file.include?("-")
            begin
              Kernel.require(file.tr("-", "/"))
            rescue LoadError => e
              raise unless e.path == file.tr("-", "/")
            end
          end
        end
      end
    end

    def root
      Kernel.require "pathname"
      Pathname.new(File.dirname(gemfile))
    end

    def default_gemfile
      Kernel.require "pathname"
      Pathname.new(gemfile)
    end

    def with_unbundled_env
      yield
    end
    alias with_original_env with_unbundled_env
    alias with_clean_env with_unbundled_env

    private

    def gemfile
      return File.expand_path(ENV["BUNDLE_GEMFILE"]) if ENV["BUNDLE_GEMFILE"]
      dir = Dir.pwd
      loop do
        %w[Gemfile gems.rb].each do |name|
          path = File.join(dir, name)
          return path if File.file?(path)
        end
        parent = File.dirname(dir)
        raise GemfileNotFound, "Could not locate Gemfile" if parent == dir
        dir = parent
      end
    end

    def resolve
      output = `bundle exec ruby #{RESOLVE_SCRIPT}`
      unless $?.success?
        raise BundlerError, "`bundle exec ruby` failed with exit #{$?.exitstatus}; topaz needs CRuby's bundle on PATH to resolve the Gemfile"
      end

      gems = []
      stdlib = []
      @dependencies = []
      output.each_line do |line|
        fields = line.chomp.split("\t", -1)
        case fields[0]
        when "path" then gems << fields[1]
        when "stdlib" then stdlib << fields[1]
        when "dep"
          name, groups, mode, files = fields[1..4]
          @dependencies << Dependency.new(name, groups.split(","), mode == "explicit", files.split(","))
        end
      end

      $LOAD_PATH.unshift(*(gems - $LOAD_PATH))
      $LOAD_PATH.concat(stdlib - $LOAD_PATH)
      Gem.refresh

      Kernel.require "topaz/concurrent_ruby" if gems.any? { |p| p.include?("/concurrent-ruby-") }
    end
  end
end
