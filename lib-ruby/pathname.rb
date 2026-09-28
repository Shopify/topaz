# Pathname, which is part of the core in Ruby 4.0 (topaz autoloads it).
class Pathname
  SEPARATOR_PAT = %r{/}
  SAME_PATHS = proc { |a, b| a == b }
  TO_PATH = :to_path

  def initialize(path)
    path = path.to_path if path.respond_to?(:to_path)
    path = Topaz.convert_type(path, String, :to_str)
    raise ArgumentError, "pathname contains null byte" if path.include?("\0")
    @path = path.dup
  end

  def self.getwd
    new(Dir.getwd)
  end

  def self.pwd
    getwd
  end

  def self.glob(*args, **opts, &block)
    if block
      Dir.glob(*args, **opts) { |f| yield new(f) }
      nil
    else
      Dir.glob(*args, **opts).map { |f| new(f) }
    end
  end

  def self.mktmpdir(*args, &block)
    require "tmpdir"
    if block
      Dir.mktmpdir(*args) { |dir| yield new(dir) }
    else
      new(Dir.mktmpdir(*args))
    end
  end

  def to_s
    @path.dup
  end
  alias to_path to_s

  def path
    @path
  end
  protected :path

  def inspect
    "#<#{self.class}:#{@path}>"
  end

  def freeze
    @path.freeze
    super
  end

  def ==(other)
    other.is_a?(Pathname) && @path == other.path
  end
  alias === ==
  alias eql? ==

  def <=>(other)
    return nil unless other.is_a?(Pathname)
    @path.tr("/", "\0") <=> other.path.tr("/", "\0")
  end

  def hash
    @path.hash
  end

  def sub(*args, &block)
    self.class.new(block ? @path.sub(*args, &block) : @path.sub(*args))
  end

  def sub_ext(repl)
    ext = File.extname(@path)
    self.class.new(@path.chomp(ext) + repl)
  end

  # Path arithmetic

  def root?
    @path.start_with?("/") && @path.delete("/").empty?
  end

  def absolute?
    @path.start_with?("/")
  end

  def relative?
    !absolute?
  end

  def each_filename
    return to_enum(:each_filename) unless block_given?
    @path.split("/").each { |f| yield f unless f.empty? }
    nil
  end

  def descend
    return to_enum(:descend) unless block_given?
    vs = []
    ascend { |v| vs << v }
    vs.reverse_each { |v| yield v }
    nil
  end

  def ascend
    return to_enum(:ascend) unless block_given?
    path = @path
    yield self
    while (r = __topaz_chop_basename(path))
      path = r[0]
      break if path.empty?
      yield self.class.new(path.sub(%r{(?<=.)/+\z}, ""))
    end
  end

  def +(other)
    other = Pathname.new(other) unless other.is_a?(Pathname)
    Pathname.new(__topaz_plus(@path, other.to_s))
  end
  alias / +

  def join(*args)
    return self if args.empty?
    result = args.pop
    result = Pathname.new(result) unless result.is_a?(Pathname)
    return result if result.absolute?
    args.reverse_each do |arg|
      arg = Pathname.new(arg) unless arg.is_a?(Pathname)
      result = arg + result
      return result if result.absolute?
    end
    self + result
  end

  def parent
    self + ".."
  end

  def cleanpath(consider_symlink = false)
    names = []
    @path.split("/").each do |part|
      next if part.empty? || part == "."
      if part == ".." && !names.empty? && names.last != ".."
        names.pop
      elsif part == ".." && absolute?
        next
      else
        names << part
      end
    end
    joined = names.join("/")
    if absolute?
      Pathname.new("/" + joined)
    else
      Pathname.new(joined.empty? ? "." : joined)
    end
  end

  def relative_path_from(base_directory)
    base_directory = Pathname.new(base_directory) unless base_directory.is_a?(Pathname)
    dest = cleanpath.to_s
    base = base_directory.cleanpath.to_s
    if absolute? != base_directory.absolute?
      raise ArgumentError, "different prefix: #{dest.inspect} and #{base_directory.inspect}"
    end
    dest_names = dest.split("/").reject(&:empty?)
    base_names = base.split("/").reject(&:empty?)
    dest_names.delete(".")
    base_names.delete(".")
    while !dest_names.empty? && !base_names.empty? && dest_names.first == base_names.first
      dest_names.shift
      base_names.shift
    end
    if base_names.include?("..")
      raise ArgumentError, "base_directory has ..: #{base_directory}"
    end
    names = [".."] * base_names.size + dest_names
    Pathname.new(names.empty? ? "." : names.join("/"))
  end

  def children(with_directory = true)
    with_directory = false if @path == "."
    Dir.entries(@path).reject { |e| e == "." || e == ".." }.sort.map do |e|
      with_directory ? self.class.new(File.join(@path, e)) : self.class.new(e)
    end
  end

  def each_child(with_directory = true, &block)
    children(with_directory).each(&block)
  end

  def mountpoint?
    stat1 = lstat
    stat2 = parent.lstat
    stat1.dev != stat2.dev || stat1.ino == stat2.ino
  rescue Errno::ENOENT
    false
  end

  # File and directory operations

  def basename(*args)
    self.class.new(File.basename(@path, *args))
  end

  def dirname
    self.class.new(File.dirname(@path))
  end

  def extname
    File.extname(@path)
  end

  def expand_path(*args)
    self.class.new(File.expand_path(@path, *args))
  end

  def split
    [dirname, basename]
  end

  def realpath(*args)
    self.class.new(File.realpath(@path, *args))
  end

  def realdirpath(*args)
    self.class.new(File.realdirpath(@path, *args))
  end

  def each_line(*args, &block)
    File.foreach(@path, *args, &block)
  end

  def read(*args)
    File.read(@path, *args)
  end

  def binread(*args)
    File.binread(@path, *args)
  end

  def readlines(*args)
    File.readlines(@path, *args)
  end

  def write(*args)
    File.write(@path, *args)
  end

  def binwrite(*args)
    File.binwrite(@path, *args)
  end

  def sysopen(*args)
    IO.sysopen(@path, *args)
  end

  def open(*args, &block)
    File.open(@path, *args, &block)
  end

  %w[atime birthtime ctime mtime ftype lstat stat size truncate].each do |name|
    define_method(name) { |*args| File.__send__(name, @path, *args) }
  end

  def readlink
    self.class.new(File.readlink(@path))
  end

  def chmod(mode)
    File.chmod(mode, @path)
  end

  def lchmod(mode)
    File.lchmod(mode, @path)
  end

  def chown(owner, group)
    File.chown(owner, group, @path)
  end

  def lchown(owner, group)
    File.lchown(owner, group, @path)
  end

  def fnmatch(pattern, *args)
    File.fnmatch(pattern, @path, *args)
  end
  alias fnmatch? fnmatch

  def make_link(old)
    File.link(old, @path)
  end

  def make_symlink(old)
    File.symlink(old, @path)
  end

  def rename(to)
    File.rename(@path, to)
  end

  def utime(atime, mtime)
    File.utime(atime, mtime, @path)
  end

  def lutime(atime, mtime)
    File.lutime(atime, mtime, @path)
  end

  %w[blockdev? chardev? executable? executable_real? exist? grpowned? directory? file?
     pipe? socket? owned? readable? world_readable? readable_real? setuid? setgid? size?
     sticky? symlink? writable? world_writable? writable_real? zero?].each do |name|
    define_method(name) { File.__send__(name, @path) }
  end

  def empty?
    directory? ? Dir.empty?(@path) : File.empty?(@path)
  end

  def glob(*args, **opts)
    base = File.expand_path(@path)
    if block_given?
      Dir.glob(*args, base: base, **opts) { |f| yield self + f }
      nil
    else
      Dir.glob(*args, base: base, **opts).map { |f| self + f }
    end
  end

  def entries
    Dir.entries(@path).map { |f| self.class.new(f) }
  end

  def mkdir(*args)
    Dir.mkdir(@path, *args)
  end

  def rmdir
    Dir.rmdir(@path)
  end

  def opendir(&block)
    Dir.open(@path, &block)
  end

  def each_entry(&block)
    Dir.foreach(@path) { |f| yield self.class.new(f) }
  end

  def mkpath(mode: nil)
    require "fileutils"
    FileUtils.mkdir_p(@path, mode: mode)
    self
  end

  def rmtree(noop: nil, verbose: nil, secure: nil)
    require "fileutils"
    FileUtils.rm_rf(@path, noop: noop, verbose: verbose, secure: secure)
    self
  end

  def unlink
    if Dir.exist?(@path)
      Dir.unlink(@path)
    else
      File.unlink(@path)
    end
  end
  alias delete unlink

  def find(ignore_error: true)
    return to_enum(:find, ignore_error: ignore_error) unless block_given?
    require "find"
    if @path == "."
      Find.find(@path, ignore_error: ignore_error) { |f| yield self.class.new(f.sub(%r{\A\./}, "")) }
    else
      Find.find(@path, ignore_error: ignore_error) { |f| yield self.class.new(f) }
    end
  end

  undef =~ if method_defined?(:=~)

  private

  def __topaz_chop_basename(path)
    base = File.basename(path)
    if path.empty? || base == "/" || base.empty?
      nil
    else
      [path[0, path.rindex(base)], base]
    end
  end

  def __topaz_plus(path1, path2)
    return path2 if path2.start_with?("/")
    return path1 if path2.empty? || path2 == "."
    prefix = path1
    parts = path2.split("/")
    parts.each do |part|
      next if part.empty? || part == "."
      if part == ".."
        if prefix.empty? || prefix == "."
          prefix = ".."
        elsif prefix == "/"
          prefix = "/"
        elsif File.basename(prefix) == ".."
          prefix = File.join(prefix, "..")
        else
          d = File.dirname(prefix)
          prefix = d
        end
      else
        prefix = prefix == "." || prefix.empty? ? part : File.join(prefix, part)
      end
    end
    prefix.empty? ? "." : prefix
  end
end
