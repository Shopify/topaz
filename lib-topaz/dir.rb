class Dir
  def self.exists?(dirname)
    !!new(dirname)
  rescue Errno::ENOENT, Errno::ENOTDIR
    false
  end

  class << self
    alias :exist? :exists?
  end

  def self.open(path, opts = nil, &block)
    dir = new(path)
    if block
      value = nil

      begin
        value = yield dir
      ensure
        dir.close
      end

      value
    else
      dir
    end
  end

  def self.foreach(path, &block)
    return self.enum_for(:foreach, path) unless block

    open(path) do |dir|
      while s = dir.read
        yield s
      end
    end

    nil
  end
end

class Dir
  class << self
    alias __topaz_glob glob
    private :__topaz_glob

    # Dir.glob(patterns, flags = 0, base: nil, sort: true): with base,
    # relative patterns are matched from that directory and the results
    # are relative to it.
    def glob(pattern, flags = 0, base: nil, sort: true, &block)
      patterns = pattern.is_a?(Array) ? pattern : [pattern]
      prefix = nil
      if base
        base = base.to_path if base.respond_to?(:to_path)
        prefix = base.empty? || base.end_with?("/") ? base : "#{base}/"
      end
      results = patterns.flat_map do |pat|
        pat = pat.to_path if pat.respond_to?(:to_path)
        found = if prefix && !prefix.empty? && !pat.start_with?("/")
                  __topaz_glob(prefix + pat, flags).map { |file| file.delete_prefix(prefix) }
                else
                  __topaz_glob(pat, flags)
                end
        # Each pattern's matches are sorted, in the order of the patterns.
        sort ? found.sort : found
      end
      return results unless block
      results.each(&block)
      nil
    end

    def [](*patterns, base: nil, sort: true)
      glob(patterns, 0, base: base, sort: sort)
    end
  end
end

class Dir
  # Entries without "." and "..".
  def self.children(dirname, encoding: nil)
    entries(dirname).reject { |name| name == "." || name == ".." }
  end

  def self.each_child(dirname, encoding: nil, &block)
    return enum_for(:each_child, dirname) unless block
    children(dirname).each(&block)
    nil
  end

  def self.empty?(dirname)
    File.directory?(dirname) && children(dirname).empty?
  end

  def children
    entries = []
    each { |name| entries << name unless name == "." || name == ".." }
    entries
  end

  def each_child(&block)
    return enum_for(:each_child) unless block
    children.each(&block)
    self
  end
end

class Dir
  include Enumerable

  def each
    return enum_for(:each) unless block_given?
    while (name = read)
      yield name
    end
    self
  end

  def to_path
    path
  end

  def fileno
    raise NotImplementedError, "Dir#fileno is not supported by topaz"
  end

  def self.home(user = nil)
    raise ArgumentError, "user homes are not supported by topaz" if user
    ENV["HOME"] || Etc.getpwuid&.dir
  end

  def self.tmpdir
    ENV["TMPDIR"] || "/tmp"
  end unless respond_to?(:tmpdir)
end
