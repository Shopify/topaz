# zlib (zlib.so) on libz through FFI: crc32/adler32, Deflate and Inflate
# streams, and gzip reading and writing. Found by name, or through
# TOPAZ_LIBZ.
#
# z_stream's layout is zlib's on 64-bit Linux.
require "ffi"
require "stringio"

module Zlib
  module LibZ
    extend FFI::Library

    candidates = [ENV["TOPAZ_LIBZ"], "libz.so.1", "libz.so", "z"].compact
    loaded = false
    candidates.each do |name|
      begin
        ffi_lib name
        loaded = true
        break
      rescue LoadError
      end
    end
    raise LoadError, "cannot load libz (set TOPAZ_LIBZ to its path)" unless loaded

    attach_function :zlibVersion, [], :string
    attach_function :crc32, [:ulong, :pointer, :uint], :ulong
    attach_function :adler32, [:ulong, :pointer, :uint], :ulong
    attach_function :deflateInit2_, [:pointer, :int, :int, :int, :int, :int, :string, :int], :int
    attach_function :deflate, [:pointer, :int], :int
    attach_function :deflateEnd, [:pointer], :int
    attach_function :inflateInit2_, [:pointer, :int, :string, :int], :int
    attach_function :inflate, [:pointer, :int], :int
    attach_function :inflateEnd, [:pointer], :int

    STREAM_SIZE = 112
    NEXT_IN = 0
    AVAIL_IN = 8
    TOTAL_IN = 16
    NEXT_OUT = 24
    AVAIL_OUT = 32
    TOTAL_OUT = 40
    MSG = 48
    ADLER = 96

    def self.buffer(string)
      memory = FFI::MemoryPointer.new(:char, string.bytesize + 1)
      memory.put_bytes(0, string, 0, string.bytesize) if string.bytesize > 0
      memory
    end
  end

  VERSION = "3.2.3"
  ZLIB_VERSION = LibZ.zlibVersion

  NO_COMPRESSION = 0
  BEST_SPEED = 1
  BEST_COMPRESSION = 9
  DEFAULT_COMPRESSION = -1
  FILTERED = 1
  HUFFMAN_ONLY = 2
  RLE = 3
  FIXED = 4
  DEFAULT_STRATEGY = 0
  MAX_WBITS = 15
  DEF_MEM_LEVEL = 8
  MAX_MEM_LEVEL = 9
  NO_FLUSH = 0
  PARTIAL_FLUSH = 1
  SYNC_FLUSH = 2
  FULL_FLUSH = 3
  FINISH = 4
  BLOCK = 5
  BINARY = 0
  ASCII = 1
  TEXT = 1
  UNKNOWN = 2
  OS_CODE = 3
  OS_UNIX = 3

  class Error < StandardError; end
  class StreamEnd < Error; end
  class NeedDict < Error; end
  class DataError < Error; end
  class StreamError < Error; end
  class MemError < Error; end
  class BufError < Error; end
  class VersionError < Error; end
  class InProgressError < Error; end

  Z_OK = 0
  Z_STREAM_END = 1
  Z_NEED_DICT = 2
  Z_BUF_ERROR = -5

  def self.crc32(string = nil, crc = 0)
    return 0 if string.nil?
    string = string.to_s
    LibZ.crc32(crc, LibZ.buffer(string), string.bytesize)
  end

  def self.adler32(string = nil, adler = 1)
    return 1 if string.nil?
    string = string.to_s
    LibZ.adler32(adler, LibZ.buffer(string), string.bytesize)
  end

  def self.zlib_version
    ZLIB_VERSION
  end

  def self.__raise(code, stream)
    message = stream.null? ? nil : stream.get_pointer(LibZ::MSG)
    message = message && !message.null? ? message.get_string(0) : nil
    case code
    when Z_NEED_DICT then raise NeedDict, message || "need dictionary"
    when -2 then raise StreamError, message || "stream error"
    when -3 then raise DataError, message || "invalid compressed data -- format violated"
    when -4 then raise MemError, message || "insufficient memory"
    when Z_BUF_ERROR then raise BufError, message || "buffer error"
    when -6 then raise VersionError, message || "incompatible version"
    else raise Error, message || "unknown zlib error #{code}"
    end
  end

  class ZStream
    CHUNK = 16384

    def initialize
      @stream = FFI::MemoryPointer.new(:char, LibZ::STREAM_SIZE)
      @output = "".b
      @finished = false
      @closed = false
      @input = nil
    end

    def total_in
      @stream.get_uint64(LibZ::TOTAL_IN)
    end

    def total_out
      @stream.get_uint64(LibZ::TOTAL_OUT)
    end

    def adler
      @stream.get_uint64(LibZ::ADLER)
    end

    def avail_in
      @stream.get_uint32(LibZ::AVAIL_IN)
    end

    def finished?
      @finished
    end
    alias stream_end? finished?

    def closed?
      @closed
    end
    alias ended? closed?

    def flush_next_out
      out = @output
      @output = "".b
      out
    end

    def close
      __end unless @closed
      @closed = true
      nil
    end
    alias end close

    def finish
      __run("".b, Zlib::FINISH)
      flush_next_out
    end

    private

    # Feeds data through the stream (deflate or inflate) with flush,
    # collecting the output. Returns whatever input was left unread after
    # the end of the stream.
    def __run(data, flush)
      raise Zlib::Error, "stream is not ready" if @closed
      data = data.to_s.b
      input = LibZ.buffer(data)
      @stream.put_pointer(LibZ::NEXT_IN, input)
      @stream.put_uint32(LibZ::AVAIL_IN, data.bytesize)
      out = FFI::MemoryPointer.new(:char, CHUNK)
      while true
        @stream.put_pointer(LibZ::NEXT_OUT, out)
        @stream.put_uint32(LibZ::AVAIL_OUT, CHUNK)
        code = __step(flush)
        produced = CHUNK - @stream.get_uint32(LibZ::AVAIL_OUT)
        @output << out.get_bytes(0, produced) if produced > 0
        if code == Z_STREAM_END
          @finished = true
          left = @stream.get_uint32(LibZ::AVAIL_IN)
          return left > 0 ? data.byteslice(data.bytesize - left, left) : nil
        end
        if code == Z_BUF_ERROR
          break
        elsif code != Z_OK
          Zlib.__raise(code, @stream)
        end
        break if @stream.get_uint32(LibZ::AVAIL_OUT) != 0 && @stream.get_uint32(LibZ::AVAIL_IN) == 0 &&
                 (flush != Zlib::FINISH || __inflating?)
      end
      nil
    end

    def __inflating?
      false
    end
  end

  class Deflate < ZStream
    def self.deflate(string, level = DEFAULT_COMPRESSION)
      stream = new(level)
      result = stream.deflate(string, FINISH)
      stream.close
      result
    end

    def initialize(level = DEFAULT_COMPRESSION, wbits = MAX_WBITS, memlevel = DEF_MEM_LEVEL,
                   strategy = DEFAULT_STRATEGY)
      super()
      level = DEFAULT_COMPRESSION if level.nil?
      code = LibZ.deflateInit2_(@stream, level, 8, wbits, memlevel, strategy, ZLIB_VERSION,
                                LibZ::STREAM_SIZE)
      Zlib.__raise(code, @stream) if code != Z_OK
    end

    def deflate(string, flush = NO_FLUSH)
      __run(string, flush)
      flush_next_out
    end

    def <<(string)
      __run(string, NO_FLUSH)
      self
    end

    def flush(flush = SYNC_FLUSH)
      __run("".b, flush) unless flush == NO_FLUSH
      flush_next_out
    end

    def params(level, strategy)
      nil
    end

    private

    def __step(flush)
      LibZ.deflate(@stream, flush)
    end

    def __end
      LibZ.deflateEnd(@stream)
    end
  end

  class Inflate < ZStream
    def self.inflate(string)
      stream = new
      result = stream.inflate(string)
      stream.finish
      stream.close
      result
    end

    def initialize(wbits = MAX_WBITS)
      super()
      code = LibZ.inflateInit2_(@stream, wbits, ZLIB_VERSION, LibZ::STREAM_SIZE)
      Zlib.__raise(code, @stream) if code != Z_OK
    end

    def inflate(string, buffer: nil)
      if string.nil?
        result = finish
      else
        @unused = __run(string, SYNC_FLUSH) unless @finished
        result = flush_next_out
      end
      buffer ? buffer.replace(result) : result
    end

    def <<(string)
      @unused = __run(string, SYNC_FLUSH) unless @finished
      self
    end

    def finish
      raise BufError, "buffer error" unless @finished || @output.bytesize > 0 || total_in == 0
      flush_next_out
    end

    def unused
      @unused
    end

    def sync_point?
      false
    end

    private

    def __inflating?
      true
    end

    def __step(flush)
      LibZ.inflate(@stream, flush)
    end

    def __end
      LibZ.inflateEnd(@stream)
    end
  end

  def self.deflate(string, level = DEFAULT_COMPRESSION)
    Deflate.deflate(string, level)
  end

  def self.inflate(string)
    Inflate.inflate(string)
  end

  def self.gzip(string, level: nil, strategy: nil, mtime: nil, orig_name: nil, comment: nil)
    io = StringIO.new("".b)
    gz = GzipWriter.new(io, level, strategy)
    gz.mtime = mtime if mtime
    gz.write(string)
    gz.finish
    io.string
  end

  def self.gunzip(string)
    GzipReader.new(StringIO.new(string.to_s.b)).read
  end

  class GzipFile
    class Error < Zlib::Error
      attr_reader :input
    end
    class NoFooter < Error; end
    class CRCError < Error; end
    class LengthError < Error; end

    def self.wrap(*args, **opts)
      gz = new(*args, **opts)
      return gz unless block_given?
      begin
        yield gz
      ensure
        gz.close unless gz.closed?
      end
    end

    attr_accessor :mtime, :orig_name, :comment, :sync
    attr_reader :level, :os_code

    def to_io
      @io
    end

    def closed?
      @closed
    end

    def finish
      __finish
      @closed = true
      @io
    end

    def close
      io = finish
      io.close if io.respond_to?(:close)
      io
    end
  end

  class GzipWriter < GzipFile
    def self.open(filename, level = nil, strategy = nil, **opts, &block)
      wrap(File.open(filename, "wb"), level, strategy, **opts, &block)
    end

    def initialize(io, level = nil, strategy = nil, **opts)
      @io = io
      @level = level || DEFAULT_COMPRESSION
      @os_code = OS_CODE
      @deflate = Deflate.new(@level, MAX_WBITS + 16, DEF_MEM_LEVEL, strategy || DEFAULT_STRATEGY)
      @closed = false
      @pos = 0
    end

    def write(*strings)
      total = 0
      strings.each do |string|
        string = string.to_s
        @io.write(@deflate.deflate(string))
        total += string.bytesize
      end
      @pos += total
      total
    end

    def <<(string)
      write(string)
      self
    end

    def print(*args)
      write(*args.map(&:to_s))
      nil
    end

    def puts(*args)
      args = [""] if args.empty?
      args.flatten.each { |a| a = a.to_s; write(a.end_with?("\n") ? a : a + "\n") }
      nil
    end

    def printf(*args)
      write(format(*args))
      nil
    end

    def putc(char)
      write(char.is_a?(Integer) ? char.chr : char.to_s[0])
      char
    end

    def flush(flush = SYNC_FLUSH)
      @io.write(@deflate.flush(flush)) unless flush == NO_FLUSH
      @io.flush if @io.respond_to?(:flush)
      self
    end

    def pos
      @pos
    end
    alias tell pos

    private

    def __finish
      return if @closed
      @io.write(@deflate.finish)
      @deflate.close
    end
  end

  class GzipReader < GzipFile
    include Enumerable

    def self.open(filename, **opts, &block)
      wrap(File.open(filename, "rb"), **opts, &block)
    end

    def self.zcat(io, **opts, &block)
      result = +""
      until io.eof?
        gz = new(io, **opts)
        data = gz.read
        block ? yield(data) : result << data
        rest = gz.unused
        gz.finish
        break unless rest
        io = StringIO.new(rest)
      end
      block ? nil : result
    end

    def initialize(io, **opts)
      @io = io
      @os_code = OS_CODE
      @closed = false
      @inflate = Inflate.new(MAX_WBITS + 16)
      @buffer = "".b
      @eof = false
      @pos = 0
      @external_encoding = opts[:external_encoding] || opts[:encoding]
      __fill_all
    end

    def read(length = nil, outbuf = nil)
      data = if length.nil?
               result = @buffer
               @buffer = "".b
               result
             else
               return nil if @buffer.empty? && length > 0
               result = @buffer.byteslice(0, length)
               @buffer = @buffer.byteslice(length, @buffer.bytesize - length) || "".b
               result
             end
      @pos += data.bytesize
      data = data.force_encoding(@external_encoding || Encoding.default_external) if length.nil?
      outbuf ? outbuf.replace(data) : data
    end

    def readpartial(length, outbuf = nil)
      raise EOFError, "end of file reached" if @buffer.empty?
      read(length, outbuf)
    end

    def getc
      return nil if @buffer.empty?
      char = @buffer.dup.force_encoding(Encoding::UTF_8)[0]
      read(char.bytesize).force_encoding(Encoding::UTF_8)
    end

    def readchar
      getc or raise EOFError, "end of file reached"
    end

    def getbyte
      return nil if @buffer.empty?
      read(1).getbyte(0)
    end

    def readbyte
      getbyte or raise EOFError, "end of file reached"
    end

    def each_byte
      return to_enum(:each_byte) unless block_given?
      while (byte = getbyte)
        yield byte
      end
      self
    end

    def gets(separator = $/, limit = nil)
      return nil if @buffer.empty?
      if separator.nil?
        line = read
      else
        index = @buffer.index(separator)
        length = index ? index + separator.bytesize : @buffer.bytesize
        length = limit if limit && limit < length
        line = read(length)
      end
      $. = (@lineno = lineno + 1)
      line.force_encoding(@external_encoding || Encoding.default_external)
    end

    def readline(*args)
      gets(*args) or raise EOFError, "end of file reached"
    end

    def each_line(*args)
      return to_enum(:each_line, *args) unless block_given?
      while (line = gets(*args))
        yield line
      end
      self
    end
    alias each each_line

    def readlines(*args)
      each_line(*args).to_a
    end

    def lineno
      @lineno || 0
    end

    attr_writer :lineno

    def eof?
      @buffer.empty?
    end
    alias eof eof?

    def pos
      @pos
    end
    alias tell pos

    def rewind
      raise Zlib::GzipFile::Error, "rewind is not supported"
    end

    def unused
      @inflate.unused
    end

    def ungetc(string)
      @buffer = string.to_s.b + @buffer
      nil
    end
    alias ungetbyte ungetc

    private

    def __fill_all
      data = @io.read
      data = data.to_s.b
      if data.bytesize < 10 || data.getbyte(0) != 0x1f || data.getbyte(1) != 0x8b
        raise GzipFile::Error, "not in gzip format"
      end
      begin
        @buffer = @inflate.inflate(data)
      rescue Zlib::DataError, Zlib::BufError => e
        raise GzipFile::Error, e.message
      end
      raise GzipFile::NoFooter, "footer is not found" unless @inflate.finished?
    end

    def __finish
      return if @closed
      @inflate.close
    end
  end
end
