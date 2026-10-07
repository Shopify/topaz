# Finds the C libraries that topaz's replacements for C extensions
# (lib-ruby/ext) bind through FFI.
#
# A library is looked for, in this order: at the path in its TOPAZ_LIB*
# environment variable; in Homebrew's library directories (including
# keg-only formulas' under opt/), which macOS's dyld does not search; by
# name through the system's dynamic linker; and, for a library that no
# system ships but a gem bundles the sources of (bcrypt's crypt_blowfish,
# markly's cmark-gfm), by building it from those sources with cc, once,
# into ~/.cache/topaz.
require "ffi"
require "fileutils"

module Topaz
  module NativeLibrary
    class << self
      # Loads the library (see find) into mod, an FFI::Library.
      def load(mod, what, **options)
        mod.ffi_lib find(what, **options)
      end

      # The name or path to dlopen for the library called what (for
      # messages, e.g. "libyaml"), or raises LoadError.
      #
      # names:  the library's names: Linux sonames ("libyaml-0.so.2") and
      #         the bare name FFI maps to the platform's convention
      #         ("yaml", so libyaml.so or libyaml.dylib).
      # env:    the environment variable that may name the library's path.
      # system: whether to look for it by name through the dynamic
      #         linker. False for a library of which macOS ships only a
      #         stub that aborts the process when loaded (libcrypto).
      # build:  a proc that builds the library (see build) and returns
      #         its path, or nil when it cannot.
      def find(what, names:, env: nil, system: true, build: nil)
        candidates = []
        candidates << ENV[env] if env && ENV[env]
        candidates.concat(homebrew_paths(names))
        candidates.concat(names) if system
        found = candidates.find { |name| openable?(name) }
        return found if found

        if build && (path = build.call)
          return path if openable?(path)
        end
        hint = env ? " (set #{env} to its path)" : ""
        raise LoadError, "cannot load #{what}#{hint}"
      end

      # Builds lib<name>.<so|dylib> from the sources of the gem called
      # gem_name, which must be on the load path, into
      # cache_dir/<gem>-<version>/, unless it is already there. sources
      # and exclude are paths or globs relative to the gem's directory,
      # include directories there to add to the include path, flags
      # extra compiler flags, and stub_headers headers the sources include
      # but do not need (CRuby's), provided empty. Returns the library's
      # path, or nil when the gem is not on the load path.
      def build(gem_name, name, sources:, exclude: [], include: [], flags: [], stub_headers: [])
        spec = defined?(Gem) && Gem.loaded_specs[gem_name]
        return nil unless spec

        dir = File.join(cache_dir, spec.full_name)
        path = File.join(dir, "lib#{name}.#{FFI::Platform::LIBSUFFIX}")
        return path if File.file?(path)

        gem_dir = spec.full_gem_path
        files = sources.flat_map { |s| Dir.glob(File.join(gem_dir, s)).sort }
        files -= exclude.flat_map { |e| Dir.glob(File.join(gem_dir, e)) }
        raise LoadError, "no sources for #{name} in #{gem_dir}" if files.empty?

        include_dir = File.join(dir, "include")
        FileUtils.mkdir_p(include_dir)
        stub_headers.each do |header|
          stub = File.join(include_dir, header)
          FileUtils.mkdir_p(File.dirname(stub))
          File.write(stub, "") unless File.file?(stub)
        end

        command = [ENV["CC"] || "cc", "-O2", "-fPIC", "-shared", "-w", *flags,
                   *include.map { |i| "-I#{File.join(gem_dir, i)}" }, "-I#{include_dir}",
                   "-o", path, *files]
        $stderr.puts "topaz: building #{path} from #{spec.full_name}'s sources"
        unless system(*command)
          File.delete(path) if File.file?(path)
          raise LoadError, "building #{path} failed: #{command.join(" ")}"
        end
        path
      end

      def cache_dir
        ENV["TOPAZ_CACHE_DIR"] || File.join(ENV["XDG_CACHE_HOME"] || File.expand_path("~/.cache"), "topaz")
      end

      private

      def openable?(name)
        [name, FFI.map_library_name(name)].uniq.any? do |candidate|
          begin
            FFI::DynamicLibrary.open(candidate, FFI::DynamicLibrary::RTLD_LAZY | FFI::DynamicLibrary::RTLD_LOCAL)
            true
          rescue LoadError
            false
          end
        end
      end

      # The files among Homebrew's libraries that the bare names map to.
      def homebrew_paths(names)
        dirs = library_dirs
        return [] if dirs.empty?
        files = names.reject { |n| n.include?(".so") }.map { |n| FFI.map_library_name(n) }
        dirs.product(files).map { |dir, file| File.join(dir, file) }.select { |path| File.file?(path) }
      end

      def library_dirs
        @library_dirs ||= begin
          prefixes = [ENV["HOMEBREW_PREFIX"]].compact
          prefixes.concat(%w[/opt/homebrew /usr/local]) if FFI::Platform::IS_MAC
          prefixes.uniq.select { |p| File.directory?(p) }.flat_map do |prefix|
            [File.join(prefix, "lib")] + Dir.glob(File.join(prefix, "opt", "*", "lib")).sort
          end
        end
      end
    end
  end
end
