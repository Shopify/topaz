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
