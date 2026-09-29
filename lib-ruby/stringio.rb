# StringIO: an IO over a String.
class StringIO
  include Enumerable

  VERSION = "3.1.2"

  def self.open(*args)
    io = new(*args)
    return io unless block_given?
    begin
      yield io
    ensure
      io.close unless io.closed?
    end
  end

  attr_reader :lineno

  def initialize(string = nil, mode = nil, **opts)
    mode = opts[:mode] if mode.nil? && opts[:mode]
    if string.nil?
      @string = +""
      mode ||= "r+"
    else
      @string = Topaz.convert_type(string, String, :to_str)
      mode ||= @string.frozen? ? "r" : "r+"
    end
    @pos = 0
    @lineno = 0
    @closed_read = false
    @closed_write = false
    __topaz_set_mode(mode)
    @string.replace("") if @truncate
  end

  def initialize_copy(other)
    super
    self
  end

  def string
    @string
  end

  def string=(string)
    @string = Topaz.convert_type(string, String, :to_str)
    @pos = 0
    @lineno = 0
    string
  end

  def reopen(string = nil, mode = nil)
    if string.is_a?(StringIO)
      @string = string.string
      __topaz_set_mode("r+")
    else
      initialize(string, mode)
    end
    self
  end

  # IO state

  def closed?
    @closed_read && @closed_write
  end

  def close
    @closed_read = @closed_write = true
    nil
  end

  def close_read
    raise IOError, "closing non-duplex IO for reading" unless @readable
    @closed_read = true
    nil
  end

  def close_write
    raise IOError, "closing non-duplex IO for writing" unless @writable
    @closed_write = true
    nil
  end

  def closed_read?
    @closed_read
  end

  def closed_write?
    @closed_write
  end

  def sync
    true
  end

  def sync=(value)
    value
  end

  def flush
    self
  end

  def fsync
    0
  end

  def fileno
    nil
  end

  def isatty
    false
  end
  alias tty? isatty

  def pid
    nil
  end

  def binmode
    @string.force_encoding(Encoding::BINARY) unless @string.frozen?
    self
  end

  def set_encoding(ext, *rest, **opts)
    @string.force_encoding(ext) if ext && !@string.frozen?
    self
  end

  def set_encoding_by_bom
    nil
  end

  def external_encoding
    @string.encoding
  end

  def internal_encoding
    nil
  end

  def lineno=(n)
    @lineno = n
  end

  # Positioning

  def pos
    @pos
  end
  alias tell pos

  def pos=(pos)
    raise Errno::EINVAL if pos < 0
    @pos = pos
  end

  def seek(offset, whence = IO::SEEK_SET)
    case whence
    when IO::SEEK_SET, :SET then base = 0
    when IO::SEEK_CUR, :CUR then base = @pos
    when IO::SEEK_END, :END then base = @string.bytesize
    else raise Errno::EINVAL, "invalid whence"
    end
    new_pos = base + offset
    raise Errno::EINVAL if new_pos < 0
    @pos = new_pos
    0
  end

  def rewind
    @pos = 0
    @lineno = 0
    0
  end

  def eof?
    __topaz_check_readable
    @pos >= @string.bytesize
  end
  alias eof eof?

  def size
    @string.bytesize
  end
  alias length size

  def truncate(length)
    raise Errno::EINVAL, "negative length" if length < 0
    __topaz_check_writable
    if length < @string.bytesize
      @string.replace(@string.byteslice(0, length))
    else
      @string << "\0" * (length - @string.bytesize)
    end
    0
  end

  # Writing

  def write(*objs)
    __topaz_check_writable
    written = 0
    objs.each do |obj|
      str = obj.to_s
      next if str.empty?
      @pos = @string.bytesize if @append
      if @pos > @string.bytesize
        @string << "\0" * (@pos - @string.bytesize)
      end
      if @pos == @string.bytesize
        @string << str
      else
        head = @string.byteslice(0, @pos)
        tail = @string.byteslice(@pos + str.bytesize, @string.bytesize) || ""
        @string.replace(head + str + tail)
      end
      @pos += str.bytesize
      written += str.bytesize
    end
    written
  end
  alias syswrite write
  alias write_nonblock write

  def <<(obj)
    write(obj)
    self
  end

  def print(*args)
    args = [$_] if args.empty?
    write(args.map(&:to_s).join($, || ""))
    write($\) if $\
    nil
  end

  def puts(*args)
    if args.empty?
      write("\n")
      return nil
    end
    args.each do |arg|
      if arg.is_a?(Array)
        arg.flatten.each { |a| puts(a) }
        next
      end
      line = arg.nil? ? "" : arg.to_s
      line += "\n" unless line.end_with?("\n")
      write(line)
    end
    nil
  end

  def printf(format_string, *args)
    write(format(format_string, *args))
    nil
  end

  def putc(obj)
    write(obj.is_a?(Integer) ? (obj & 0xff).chr : obj.to_s[0])
    obj
  end

  # Reading

  def read(length = nil, buffer = nil)
    __topaz_check_readable
    rest = @pos >= @string.bytesize ? "" : @string.byteslice(@pos, @string.bytesize - @pos)
    if length.nil?
      data = rest
      @pos = @string.bytesize if @pos < @string.bytesize
    else
      length = Topaz.convert_type(length, Integer, :to_int)
      raise ArgumentError, "negative length #{length} given" if length < 0
      if rest.empty?
        buffer&.replace("")
        return length == 0 ? "" : nil
      end
      data = rest.byteslice(0, length)
      @pos += data.bytesize
      data.force_encoding(Encoding::BINARY)
    end
    buffer ? buffer.replace(data) : data
  end

  def read_nonblock(length, buffer = nil, exception: true)
    data = read(length, buffer)
    if data.nil?
      raise EOFError, "end of file reached" if exception
      return nil
    end
    data
  end

  def readpartial(length, buffer = nil)
    data = read(length, buffer)
    raise EOFError, "end of file reached" if data.nil?
    data
  end
  alias sysread readpartial

  def pread(length, offset)
    @string.byteslice(offset, length)
  end

  def getc
    __topaz_check_readable
    return nil if @pos >= @string.bytesize
    b = @string.getbyte(@pos)
    n = b < 0x80 ? 1 : b >= 0xf0 ? 4 : b >= 0xe0 ? 3 : b >= 0xc0 ? 2 : 1
    c = @string.byteslice(@pos, n)
    @pos += c.bytesize
    c
  end

  def getbyte
    __topaz_check_readable
    return nil if @pos >= @string.bytesize
    b = @string.getbyte(@pos)
    @pos += 1
    b
  end

  def readchar
    c = getc
    raise EOFError, "end of file reached" if c.nil?
    c
  end

  def readbyte
    b = getbyte
    raise EOFError, "end of file reached" if b.nil?
    b
  end

  def ungetc(c)
    __topaz_check_readable
    return nil if c.nil?
    c = c.is_a?(Integer) ? c.chr : c.to_s
    if @pos == 0
      @string.replace(c + @string)
    elsif @pos > @string.bytesize
      @string << "\0" * (@pos - @string.bytesize)
      @pos -= c.bytesize
      @string << c
    else
      @pos -= c.bytesize
      @pos = 0 if @pos < 0
      head = @string.byteslice(0, @pos)
      tail = @string.byteslice(@pos + c.bytesize, @string.bytesize) || ""
      @string.replace(head + c + tail)
    end
    nil
  end
  alias ungetbyte ungetc

  def gets(*args, chomp: false)
    __topaz_check_readable
    sep, limit = __topaz_line_args(args)
    return nil if @pos >= @string.bytesize
    rest = @string.byteslice(@pos, @string.bytesize - @pos)
    line = if sep.nil?
      rest
    elsif sep.empty?
      # Paragraph mode.
      rest = rest.sub(/\A\n+/, "")
      skipped = @string.bytesize - @pos - rest.bytesize
      @pos += skipped
      i = rest.index(/\n\n/)
      i ? rest.byteslice(0, i + 2) : rest
    else
      i = rest.index(sep)
      i ? rest.byteslice(0, i + sep.bytesize) : rest
    end
    line = line.byteslice(0, limit) if limit && limit >= 0 && line.bytesize > limit
    @pos += line.bytesize
    if sep && sep.empty?
      extra = @string.byteslice(@pos, @string.bytesize - @pos)[/\A\n*/]
      @pos += extra.bytesize if extra
    end
    @lineno += 1
    if chomp
      if sep.nil?
        # nothing
      elsif sep.empty?
        line = line.sub(/\n+\z/, "")
      elsif line.end_with?(sep)
        line = line.byteslice(0, line.bytesize - sep.bytesize)
      end
    end
    $_ = line
    line
  end

  def readline(*args, **opts)
    line = gets(*args, **opts)
    raise EOFError, "end of file reached" if line.nil?
    line
  end

  def each_line(*args, chomp: false, &block)
    return enum_for(:each_line, *args, chomp: chomp) unless block
    while (line = gets(*args, chomp: chomp))
      block.call(line)
    end
    self
  end
  alias each each_line

  def readlines(*args, chomp: false)
    lines = []
    each_line(*args, chomp: chomp) { |line| lines << line }
    lines
  end

  def each_char(&block)
    return enum_for(:each_char) unless block
    while (c = getc)
      block.call(c)
    end
    self
  end

  def each_byte(&block)
    return enum_for(:each_byte) unless block
    while (b = getbyte)
      block.call(b)
    end
    self
  end

  def each_codepoint(&block)
    return enum_for(:each_codepoint) unless block
    each_char { |c| block.call(c.ord) }
  end

  private

  def __topaz_set_mode(mode)
    @append = false
    @truncate = false
    if mode.is_a?(Integer)
      access = mode & 3
      @readable = access == IO::RDONLY || access == IO::RDWR
      @writable = access == IO::WRONLY || access == IO::RDWR
      @append = mode & IO::APPEND != 0
      @truncate = mode & IO::TRUNC != 0
    else
      mode = mode.to_s.delete("b").delete("t")
      mode = mode.split(":").first || "r"
      case mode
      when "r" then @readable, @writable = true, false
      when "r+" then @readable, @writable = true, true
      when "w" then @readable, @writable, @truncate = false, true, true
      when "w+" then @readable, @writable, @truncate = true, true, true
      when "a" then @readable, @writable, @append = false, true, true
      when "a+" then @readable, @writable, @append = true, true, true
      else raise ArgumentError, "invalid access mode #{mode}"
      end
    end
    if @writable && @string.frozen?
      raise Errno::EACCES
    end
  end

  def __topaz_check_readable
    raise IOError, "not opened for reading" if !@readable || @closed_read
  end

  def __topaz_check_writable
    raise IOError, "not opened for writing" if !@writable || @closed_write
  end

  def __topaz_line_args(args)
    sep = $/
    limit = nil
    case args.size
    when 0
    when 1
      if args[0].nil? || args[0].is_a?(String)
        sep = args[0]
      else
        limit = Topaz.convert_type(args[0], Integer, :to_int)
      end
    else
      sep = args[0]
      limit = args[1] && Topaz.convert_type(args[1], Integer, :to_int)
    end
    [sep, limit]
  end
end
