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

  # Line reading. topaz's IO does not buffer, so a line is read in
  # chunks and what follows it is given back by seeking; where the IO
  # cannot seek (pipes, terminals) it is read a byte at a time.
  def gets(*args, chomp: false)
    raise IOError, "closed stream" if closed?
    sep, limit = __topaz_line_args(args)
    line = __topaz_read_line(sep, limit)
    if line
      self.lineno = lineno + 1
      $. = lineno
      line = __topaz_chomp_line(line, sep) if chomp
    end
    $_ = line
  end

  def readline(*args, chomp: false)
    line = gets(*args, chomp: chomp)
    raise EOFError, "end of file reached" if line.nil?
    line
  end

  def each_line(*args, chomp: false)
    return enum_for(:each_line, *args, chomp: chomp) unless block_given?
    sep, limit = __topaz_line_args(args)
    raise ArgumentError, "invalid limit: 0 for each_line" if limit == 0
    while (line = gets(sep, limit, chomp: chomp))
      yield line
    end
    self
  end
  alias each each_line

  def readlines(*args, chomp: false)
    sep, limit = __topaz_line_args(args)
    raise ArgumentError, "invalid limit: 0 for readlines" if limit == 0
    lines = []
    while (line = gets(sep, limit, chomp: chomp))
      lines << line
    end
    lines
  end

  private

  def __topaz_line_args(args)
    sep = $/
    limit = nil
    case args.size
    when 0
    when 1
      if args[0].nil? || args[0].is_a?(String)
        sep = args[0]
      elsif args[0].respond_to?(:to_str)
        sep = args[0].to_str
      else
        limit = Integer(args[0])
      end
    else
      sep = args[0].nil? ? nil : Topaz.convert_type(args[0], String, :to_str)
      limit = args[1].nil? ? nil : Integer(args[1])
    end
    limit = nil if limit && limit < 0
    [sep, limit]
  end

  def __topaz_chomp_line(line, sep)
    if sep.nil?
      line
    elsif sep == ""
      line.sub(/\n+\z/, "")
    elsif sep == "\n"
      line.chomp
    else
      line.end_with?(sep) ? line[0, line.bytesize - sep.bytesize] : line
    end
  end

  def __topaz_seekable?
    return @__topaz_seekable unless @__topaz_seekable.nil?
    @__topaz_seekable = begin
      pos
      !File.pipe?("/proc/self/fd/#{fileno}") && !tty?
    rescue SystemCallError, NotImplementedError, NoMethodError
      false
    end
  end

  def __topaz_read_line(sep, limit)
    if sep.nil?
      data = limit ? read(limit) : read
      return data.nil? || data.empty? ? nil : data
    end
    paragraph = sep == ""
    chunk_size = __topaz_seekable? ? 4096 : 1
    buffer = "".b
    if paragraph
      # Blank lines before a paragraph (and so after the last) are skipped.
      sep = "\n\n"
      byte = read(1)
      byte = read(1) while byte == "\n"
      return nil if byte.nil?
      buffer << byte
    end
    searched = 0
    while true
      if limit && buffer.bytesize >= limit
        return __topaz_take(buffer, limit)
      end
      chunk = read(chunk_size)
      break if chunk.nil?
      buffer << chunk
      index = buffer.index(sep, [searched - sep.bytesize + 1, 0].max)
      if index
        cut = index + sep.bytesize
        cut = limit if limit && limit < cut
        return __topaz_take(buffer, cut)
      end
      searched = buffer.bytesize
    end
    return nil if buffer.empty?
    return __topaz_take(buffer, limit) if limit && buffer.bytesize > limit
    buffer.force_encoding(Encoding.default_external)
  end

  # The first length bytes of buffer; the rest goes back to the file.
  def __topaz_take(buffer, length)
    rest = buffer.bytesize - length
    seek(-rest, IO::SEEK_CUR) if rest > 0
    buffer.byteslice(0, length).force_encoding(Encoding.default_external)
  end

  public

  # IO.read(name, length = nil, offset = nil, mode:, encoding:,
  # external_encoding:, ...). The text is tagged with the external
  # encoding (binary for a "b" mode).
  def self.read(name, length = nil, offset = nil, mode: "r", encoding: nil,
                external_encoding: nil, internal_encoding: nil, binmode: false, **opts)
    name = name.to_path if name.respond_to?(:to_path)
    File.open(name, mode.to_s.sub(/:.*\z/, "")) do |f|
      f.seek(offset) if offset
      data = length ? f.read(length) : f.read
      return data if data.nil?
      # A read of a given length is binary, as IO#read(length) is.
      return data.force_encoding(Encoding::ASCII_8BIT) if length
      mode_encoding = mode.to_s[/:([^:]+)/, 1]
      enc = external_encoding || (encoding && encoding.to_s.split(":").first) || mode_encoding
      if enc
        data.force_encoding(enc)
      elsif binmode || mode.to_s.include?("b")
        data.force_encoding(Encoding::ASCII_8BIT)
      else
        data.force_encoding(Encoding.default_external)
      end
      data
    end
  end

  def self.readlines(name, *args, chomp: false, **opts)
    File.open(name) do |f|
      return f.readlines(*args, chomp: chomp)
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
    return res unless block
    begin
      yield res
    ensure
      res.close unless res.closed?
    end
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

  def self.foreach(path, *args, chomp: false, **opts, &block)
    return enum_for(:foreach, path, *args, chomp: chomp) unless block
    File.open(path) { |f| f.each_line(*args, chomp: chomp, &block) }
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
