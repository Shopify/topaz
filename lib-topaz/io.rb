class IO
  class << self
    alias for_fd new
  end

  def <<(s)
    write(s)
    return self
  end

  def puts(*args)
    if args.empty?
      write("\n")
      return nil
    end

    args.flatten.each do |string|
      string = string.to_s unless string.is_a?(String)
      write(string)
      write("\n") unless string[-1] == "\n"
    end
    nil
  end

  def pos=(i)
    seek(i, IO::SEEK_SET)
  end

  def each_line(sep = $/, limit = nil)
    if sep.is_a?(Integer) && limit.nil?
      limit = sep
      sep = $/
    end

    if sep.nil?
      yield(limit ? read(limit) : read)
      return self
    end

    if limit == 0
      raise ArgumentError.new("invalid limit: 0 for each_line")
    end

    rest = ""
    nxt = read(8192)
    need_read = false
    while nxt || rest
      if nxt && need_read
        rest = rest ? rest + nxt : nxt
        nxt = read(8192)
        need_read = false
      end

      line, rest = *rest.split(sep, 2)

      if limit && line.size > limit
        left = 0
        right = limit
        while right < line.size
          yield line[left...right]
          left, right = right, right + limit
        end
        rest = line[right - limit..-1] + sep + (rest || "")
      elsif rest || nxt.nil?
        yield line
      else
        need_read = true
      end
    end
    self
  end
  alias each each_line
  alias lines each_line

  def readline(sep = $/, limit = nil)
    line = gets(sep, limit)
    raise EOFError.new("end of file reached") if line.nil?
    line
  end

  def gets(sep = $/, limit = nil)
    if sep.nil?
      return read
    end
    if sep.is_a?(Integer) && limit.nil?
      limit = sep
      sep = $/
    end
    raise IOError.new("closed stream") if closed?
    line = ""
    loop do
      c = getc
      break if c.nil? || c.empty?
      line << c
      break if c == sep || line.length == limit
    end
    $_ = line
    line.empty? ? nil : line
  end

  def readlines(sep = $/, limit = nil)
    lines = []
    each_line(sep, limit) { |line| lines << line }
    return lines
  end

  def self.read(name)
    File.open(name) do |f|
      f.read
    end
  end

  def self.readlines(name, *args)
    File.open(name) do |f|
      return f.readlines(*args)
    end
  end

  def self.popen(cmd, mode = 'r', opts = {}, &block)
    r, w = IO.pipe
    if mode != 'r' && mode != 'w' && mode != 'rb' && mode != 'wb'
      raise NotImplementedError.new("mode #{mode} for IO.popen")
    end

    pid = fork do
      if mode == 'r'
        r.close
        $stdout.reopen(w)
      else
        w.close
        $stdin.reopen(r)
      end
      exec(*cmd)
    end

    if mode == 'r'
      res = r
      w.close
    else
      res = w
      r.close
    end

    res.instance_variable_set("@pid", pid)
    block ? yield(res) : res
  end

  def self.binread(filename, length=nil, offset=0)
    File.open(filename, "rb") do |f|
      f.seek(offset)
      if length.nil?
        f.read
      else
        f.read(length)
      end
    end
  end

  def pid
    @pid
  end

  def self.try_convert(arg)
    Topaz.try_convert_type(arg, IO, :to_io)
  end

  def getbyte
    if ch = getc
      return ch.ord
    else
      return nil
    end
  end
end

# Methods topaz's IO lacked, in terms of the ones it has.
class IO
  def sync
    @__topaz_sync.nil? ? (fileno == 2) : @__topaz_sync
  end

  def sync=(value)
    @__topaz_sync = value ? true : false
    flush if value
    value
  end

  def fsync
    flush
    0
  end
  alias fdatasync fsync

  def binmode
    self
  end

  def binmode?
    false
  end

  def set_encoding(*args, **opts)
    self
  end

  def set_encoding_by_bom
    nil
  end

  def external_encoding
    Encoding.default_external
  end

  def internal_encoding
    Encoding.default_internal
  end

  def autoclose=(value)
    @__topaz_autoclose = value
  end

  def autoclose?
    @__topaz_autoclose != false
  end

  def close_on_exec=(value)
    value
  end

  def close_on_exec?
    true
  end

  def close_read
    close
  end

  def close_write
    close
  end

  def lineno
    @__topaz_lineno || 0
  end

  def lineno=(n)
    @__topaz_lineno = n
  end

  def each_byte(&block)
    return enum_for(:each_byte) unless block
    while (b = getbyte)
      block.call(b)
    end
    self
  end

  def each_char(&block)
    return enum_for(:each_char) unless block
    while (c = getc)
      block.call(c)
    end
    self
  end

  def readbyte
    b = getbyte
    raise EOFError, "end of file reached" if b.nil?
    b
  end

  def readchar
    c = getc
    raise EOFError, "end of file reached" if c.nil?
    c
  end

  def readpartial(maxlen, outbuf = nil)
    data = read(maxlen)
    raise EOFError, "end of file reached" if data.nil? || (data.empty? && maxlen > 0)
    outbuf ? outbuf.replace(data) : data
  end

  def read_nonblock(maxlen, outbuf = nil, exception: true)
    readpartial(maxlen, outbuf)
  end

  def write_nonblock(data, exception: true)
    write(data)
  end

  def sysread(maxlen, outbuf = nil)
    readpartial(maxlen, outbuf)
  end

  def syswrite(data)
    write(data)
  end

  def printf(format_string, *args)
    write(format(format_string, *args))
    nil
  end

  def putc(c)
    write(c.is_a?(Integer) ? (c & 0xff).chr : c.to_s[0])
    c
  end

  def eof?
    b = getbyte
    return true if b.nil?
    seek(-1, IO::SEEK_CUR) rescue nil
    false
  end
  alias eof eof?

  def wait_readable(timeout = nil)
    self
  end

  def wait_writable(timeout = nil)
    self
  end

  def wait(*args)
    self
  end

  def timeout
    nil
  end

  def timeout=(value)
    value
  end

  def self.write(path, data, *args, **opts)
    File.open(path, opts[:mode] || "w") { |f| f.write(data.to_s) }
  end

  def self.binwrite(path, data, *args)
    File.open(path, "wb") { |f| f.write(data.to_s) }
  end

  def self.foreach(path, *args, &block)
    return enum_for(:foreach, path, *args) unless block
    File.open(path) { |f| f.each_line(*args, &block) }
    nil
  end

  def self.select(readers, writers = nil, errors = nil, timeout = nil)
    [readers || [], writers || [], []]
  end

  def self.copy_stream(src, dst, copy_length = nil, src_offset = nil)
    src_io = src.respond_to?(:read) ? src : File.open(src, "rb")
    data = copy_length ? src_io.read(copy_length) : src_io.read
    data ||= ""
    if dst.respond_to?(:write)
      dst.write(data)
    else
      File.open(dst, "wb") { |f| f.write(data) }
    end
    data.bytesize
  end

  def self.open(*args, &block)
    io = new(*args)
    return io unless block
    begin
      yield io
    ensure
      io.close unless io.closed?
    end
  end
end

class File
  FNM_CASEFOLD = 8 unless const_defined?(:FNM_CASEFOLD)
  FNM_EXTGLOB = 16 unless const_defined?(:FNM_EXTGLOB)

  def to_path
    path
  end

  def flock(operation)
    0
  end

  def self.absolute_path(path, dir = nil)
    expand_path(path, dir)
  end

  def self.absolute_path?(path)
    path.to_s.start_with?("/")
  end

  def self.split(path)
    [dirname(path), basename(path)]
  end

  def self.empty?(path)
    zero?(path)
  end

  def self.readlink(path)
    raise NotImplementedError, "File.readlink is not supported by topaz"
  end

  def self.realdirpath(path, dir = nil)
    expand_path(path, dir)
  end

  def self.fnmatch(pattern, path, flags = 0)
    Topaz.fnmatch(pattern, path, flags)
  end

  def self.fnmatch?(pattern, path, flags = 0)
    Topaz.fnmatch(pattern, path, flags)
  end
end

module Topaz
  # File.fnmatch: *, ?, [set], {a,b} with FNM_EXTGLOB, ** with FNM_PATHNAME.
  def self.fnmatch(pattern, path, flags)
    dotmatch = flags & File::FNM_DOTMATCH != 0
    pathname = flags & File::FNM_PATHNAME != 0
    casefold = flags & File::FNM_CASEFOLD != 0
    patterns = flags & File::FNM_EXTGLOB != 0 ? expand_braces(pattern) : [pattern]
    patterns.any? do |pat|
      re = ""
      i = 0
      while i < pat.length
        c = pat[i]
        if c == "*"
          if pat[i + 1] == "*" && pathname
            re << ".*"
            i += 1
            i += 1 if pat[i + 1] == "/"
          else
            re << (pathname ? "[^/]*" : ".*")
          end
        elsif c == "?"
          re << (pathname ? "[^/]" : ".")
        elsif c == "["
          j = pat.index("]", i + 1)
          if j
            set = pat[i + 1...j]
            set = "^" + set[1..] if set.start_with?("!")
            re << "[" << set << "]"
            i = j
          else
            re << "\\["
          end
        elsif c == "\\" && flags & File::FNM_NOESCAPE == 0 && i + 1 < pat.length
          i += 1
          re << Regexp.escape(pat[i])
        else
          re << Regexp.escape(c)
        end
        i += 1
      end
      regexp = Regexp.new("\\A#{re}\\z", casefold ? Regexp::IGNORECASE : 0)
      next false if !dotmatch && path.start_with?(".") && !pat.start_with?(".")
      regexp.match?(path)
    end
  end

  def self.expand_braces(pattern)
    open = pattern.index("{")
    return [pattern] if open.nil?
    depth = 0
    close = nil
    (open...pattern.length).each do |i|
      depth += 1 if pattern[i] == "{"
      depth -= 1 if pattern[i] == "}"
      if depth == 0
        close = i
        break
      end
    end
    return [pattern] if close.nil?
    head = pattern[0...open]
    tail = pattern[close + 1..]
    alternatives = []
    depth = 0
    current = ""
    pattern[open + 1...close].each_char do |c|
      if c == "," && depth == 0
        alternatives << current
        current = ""
      else
        depth += 1 if c == "{"
        depth -= 1 if c == "}"
        current << c
      end
    end
    alternatives << current
    alternatives.flat_map { |alt| expand_braces(head + alt + tail) }
  end
end

class IO
  # The open flags, which CRuby's IO gets from File::Constants.
  [:RDONLY, :WRONLY, :RDWR, :APPEND, :CREAT, :EXCL, :TRUNC, :BINARY, :NONBLOCK,
   :NOCTTY, :SYNC].each do |name|
    const_set(name, File.const_get(name)) if File.const_defined?(name) && !const_defined?(name, false)
  end
end
