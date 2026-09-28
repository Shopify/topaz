# The C half of psych (psych.so), on libyaml through FFI. psych's own Ruby
# files (psych.rb and psych/*) run unchanged on top of this.
#
# Struct offsets and sizes are libyaml 0.2.5's on x86-64 Linux.
require "ffi"
# As psych.so does, for the parser's errors.
require "psych/syntax_error"

module Psych
  module LibYAML
    extend FFI::Library

    candidates = [ENV["TOPAZ_LIBYAML"], "libyaml-0.so.2", "libyaml.so", "yaml"].compact
    loaded = false
    candidates.each do |name|
      begin
        ffi_lib name
        loaded = true
        break
      rescue LoadError
      end
    end
    raise LoadError, "cannot load libyaml (set TOPAZ_LIBYAML to its path)" unless loaded

    attach_function :yaml_get_version, [:pointer, :pointer, :pointer], :void

    attach_function :yaml_parser_initialize, [:pointer], :int
    attach_function :yaml_parser_delete, [:pointer], :void
    attach_function :yaml_parser_set_input_string, [:pointer, :pointer, :size_t], :void
    attach_function :yaml_parser_set_encoding, [:pointer, :int], :void
    attach_function :yaml_parser_parse, [:pointer, :pointer], :int
    attach_function :yaml_event_delete, [:pointer], :void

    attach_function :yaml_emitter_initialize, [:pointer], :int
    attach_function :yaml_emitter_delete, [:pointer], :void
    attach_function :yaml_emitter_set_output_string, [:pointer, :pointer, :size_t, :pointer], :void
    attach_function :yaml_emitter_emit, [:pointer, :pointer], :int
    attach_function :yaml_emitter_flush, [:pointer], :int
    attach_function :yaml_emitter_set_canonical, [:pointer, :int], :void
    attach_function :yaml_emitter_set_indent, [:pointer, :int], :void
    attach_function :yaml_emitter_set_width, [:pointer, :int], :void
    attach_function :yaml_emitter_set_unicode, [:pointer, :int], :void

    attach_function :yaml_stream_start_event_initialize, [:pointer, :int], :int
    attach_function :yaml_stream_end_event_initialize, [:pointer], :int
    attach_function :yaml_document_start_event_initialize,
                    [:pointer, :pointer, :pointer, :pointer, :int], :int
    attach_function :yaml_document_end_event_initialize, [:pointer, :int], :int
    attach_function :yaml_scalar_event_initialize,
                    [:pointer, :pointer, :pointer, :pointer, :int, :int, :int, :int], :int
    attach_function :yaml_sequence_start_event_initialize,
                    [:pointer, :pointer, :pointer, :int, :int], :int
    attach_function :yaml_sequence_end_event_initialize, [:pointer], :int
    attach_function :yaml_mapping_start_event_initialize,
                    [:pointer, :pointer, :pointer, :int, :int], :int
    attach_function :yaml_mapping_end_event_initialize, [:pointer], :int
    attach_function :yaml_alias_event_initialize, [:pointer, :pointer], :int

    PARSER_SIZE = 480
    EMITTER_SIZE = 432
    EVENT_SIZE = 104

    # yaml_event_t: type, then the data union at 8, start_mark at 56 and
    # end_mark at 80 (each index, line, column as size_t).
    EVENT_DATA = 8
    START_MARK = 56
    END_MARK = 80

    # yaml_parser_t
    PARSER_ERROR = 0
    PARSER_PROBLEM = 8
    PARSER_PROBLEM_OFFSET = 16
    PARSER_CONTEXT = 56
    PARSER_CONTEXT_MARK = 64
    PARSER_MARK = 224

    # yaml_emitter_t
    EMITTER_PROBLEM = 8

    STREAM_START = 1
    STREAM_END = 2
    DOCUMENT_START = 3
    DOCUMENT_END = 4
    ALIAS = 5
    SCALAR = 6
    SEQUENCE_START = 7
    SEQUENCE_END = 8
    MAPPING_START = 9
    MAPPING_END = 10

    MEMORY_ERROR = 1

    def self.string_at(pointer)
      pointer.null? ? nil : pointer.get_string(0)
    end

    # A NUL-terminated copy of str, or NULL for nil.
    def self.cstring(str)
      return FFI::Pointer::NULL if str.nil?
      str = str.to_s
      memory = FFI::MemoryPointer.new(:char, str.bytesize + 1)
      memory.put_string(0, str)
      memory
    end
  end

  def self.libyaml_version
    numbers = FFI::MemoryPointer.new(:int, 3)
    LibYAML.yaml_get_version(numbers, numbers + 4, numbers + 8)
    [numbers.get_int32(0), numbers.get_int32(4), numbers.get_int32(8)]
  end

  class Parser
    ANY = 0
    UTF8 = 1
    UTF16LE = 2
    UTF16BE = 3

    def mark
      index, line, column = @__topaz_mark || [0, 0, 0]
      Mark.new(index, line, column)
    end

    private

    def _native_parse(handler, yaml, path)
      yaml = yaml.read if yaml.respond_to?(:read)
      yaml = Topaz.convert_type(yaml, String, :to_str)
      encoding = case yaml.encoding
                 when Encoding::UTF_16LE then UTF16LE
                 when Encoding::UTF_16BE then UTF16BE
                 else UTF8
                 end
      parser = FFI::MemoryPointer.new(:char, LibYAML::PARSER_SIZE)
      event = FFI::MemoryPointer.new(:char, LibYAML::EVENT_SIZE)
      input = FFI::MemoryPointer.new(:char, yaml.bytesize + 1)
      input.put_bytes(0, yaml)
      raise NoMemoryError if LibYAML.yaml_parser_initialize(parser) == 0
      begin
        LibYAML.yaml_parser_set_encoding(parser, encoding)
        LibYAML.yaml_parser_set_input_string(parser, input, yaml.bytesize)
        done = false
        until done
          if LibYAML.yaml_parser_parse(parser, event) == 0
            raise __topaz_syntax_error(parser, path)
          end
          begin
            @__topaz_mark = [parser.get_ulong(LibYAML::PARSER_MARK),
                             parser.get_ulong(LibYAML::PARSER_MARK + 8),
                             parser.get_ulong(LibYAML::PARSER_MARK + 16)]
            done = __topaz_dispatch(handler, event)
          ensure
            LibYAML.yaml_event_delete(event)
          end
        end
      ensure
        LibYAML.yaml_parser_delete(parser)
      end
      self
    end

    # Calls the handler for one event; true at the end of the stream.
    def __topaz_dispatch(handler, event)
      data = LibYAML::EVENT_DATA
      handler.event_location(event.get_ulong(LibYAML::START_MARK + 8),
                             event.get_ulong(LibYAML::START_MARK + 16),
                             event.get_ulong(LibYAML::END_MARK + 8),
                             event.get_ulong(LibYAML::END_MARK + 16))
      case event.get_int32(0)
      when LibYAML::STREAM_START
        handler.start_stream(event.get_int32(data))
      when LibYAML::DOCUMENT_START
        version_pointer = event.get_pointer(data)
        version = version_pointer.null? ? [] : [version_pointer.get_int32(0), version_pointer.get_int32(4)]
        tags = []
        start = event.get_pointer(data + 8)
        unless start.null?
          stop = event.get_pointer(data + 16).address
          address = start.address
          while address < stop
            directive = FFI::Pointer.new(address)
            tags << [LibYAML.string_at(directive.get_pointer(0)),
                     LibYAML.string_at(directive.get_pointer(8))]
            address += 16
          end
        end
        handler.start_document(version, tags, event.get_int32(data + 24) == 1)
      when LibYAML::DOCUMENT_END
        handler.end_document(event.get_int32(data) == 1)
      when LibYAML::ALIAS
        handler.alias(LibYAML.string_at(event.get_pointer(data)))
      when LibYAML::SCALAR
        length = event.get_ulong(data + 24)
        value = length == 0 ? "" : event.get_pointer(data + 16).get_bytes(0, length)
        handler.scalar(value,
                       LibYAML.string_at(event.get_pointer(data)),
                       LibYAML.string_at(event.get_pointer(data + 8)),
                       event.get_int32(data + 32) != 0,
                       event.get_int32(data + 36) != 0,
                       event.get_int32(data + 40))
      when LibYAML::SEQUENCE_START
        handler.start_sequence(LibYAML.string_at(event.get_pointer(data)),
                               LibYAML.string_at(event.get_pointer(data + 8)),
                               event.get_int32(data + 16) != 0,
                               event.get_int32(data + 20))
      when LibYAML::SEQUENCE_END
        handler.end_sequence
      when LibYAML::MAPPING_START
        handler.start_mapping(LibYAML.string_at(event.get_pointer(data)),
                              LibYAML.string_at(event.get_pointer(data + 8)),
                              event.get_int32(data + 16) != 0,
                              event.get_int32(data + 20))
      when LibYAML::MAPPING_END
        handler.end_mapping
      when LibYAML::STREAM_END
        handler.end_stream
        return true
      else
        handler.empty
      end
      false
    end

    def __topaz_syntax_error(parser, path)
      return NoMemoryError.new if parser.get_int32(LibYAML::PARSER_ERROR) == LibYAML::MEMORY_ERROR
      mark = LibYAML::PARSER_CONTEXT_MARK
      Psych::SyntaxError.new(path,
                      parser.get_ulong(mark + 8) + 1,
                      parser.get_ulong(mark + 16) + 1,
                      parser.get_ulong(LibYAML::PARSER_PROBLEM_OFFSET),
                      LibYAML.string_at(parser.get_pointer(LibYAML::PARSER_PROBLEM)),
                      LibYAML.string_at(parser.get_pointer(LibYAML::PARSER_CONTEXT)))
    end
  end

  class Handler
  end

  # Writes events to an IO. libyaml writes into a buffer that is emptied
  # into the IO after every event.
  class Emitter < Handler
    BUFFER_SIZE = 1 << 16

    def initialize(io, options = nil)
      @io = io
      @canonical = false
      @indentation = 2
      @line_width = 0
      if options
        @line_width = options.line_width
        @indentation = options.indentation
        @canonical = options.canonical ? true : false
      end
      @emitter = nil
    end

    attr_reader :canonical, :indentation, :line_width

    def canonical=(value)
      @canonical = value ? true : false
      LibYAML.yaml_emitter_set_canonical(@emitter, @canonical ? 1 : 0) if @emitter
    end

    def indentation=(value)
      @indentation = value
      LibYAML.yaml_emitter_set_indent(@emitter, value) if @emitter
    end

    def line_width=(value)
      @line_width = value
      LibYAML.yaml_emitter_set_width(@emitter, value) if @emitter
    end

    def start_stream(encoding)
      __topaz_setup
      __topaz_emit { |event| LibYAML.yaml_stream_start_event_initialize(event, encoding) }
    end

    def end_stream
      __topaz_emit { |event| LibYAML.yaml_stream_end_event_initialize(event) }
      LibYAML.yaml_emitter_flush(@emitter)
      __topaz_drain
      LibYAML.yaml_emitter_delete(@emitter)
      @emitter = nil
      self
    end

    def start_document(version, tag_directives, implicit)
      keep = []
      version_pointer = FFI::Pointer::NULL
      if version && !version.empty?
        version_pointer = FFI::MemoryPointer.new(:int, 2)
        version_pointer.put_int32(0, version[0])
        version_pointer.put_int32(4, version[1])
      end
      tags_start = tags_end = FFI::Pointer::NULL
      if tag_directives && !tag_directives.empty?
        tags_start = FFI::MemoryPointer.new(:char, 16 * tag_directives.size)
        tag_directives.each_with_index do |(handle, prefix), i|
          handle_pointer = LibYAML.cstring(handle)
          prefix_pointer = LibYAML.cstring(prefix)
          keep << handle_pointer << prefix_pointer
          tags_start.put_pointer(16 * i, handle_pointer)
          tags_start.put_pointer(16 * i + 8, prefix_pointer)
        end
        tags_end = tags_start + 16 * tag_directives.size
      end
      __topaz_emit do |event|
        LibYAML.yaml_document_start_event_initialize(event, version_pointer, tags_start, tags_end, implicit ? 1 : 0)
      end
      keep.clear
      self
    end

    def end_document(implicit)
      __topaz_emit { |event| LibYAML.yaml_document_end_event_initialize(event, implicit ? 1 : 0) }
    end

    def scalar(value, anchor, tag, plain, quoted, style)
      value = value.to_s
      value_pointer = LibYAML.cstring(value)
      anchor_pointer = LibYAML.cstring(anchor)
      tag_pointer = LibYAML.cstring(tag)
      __topaz_emit do |event|
        LibYAML.yaml_scalar_event_initialize(event, anchor_pointer, tag_pointer, value_pointer,
                                             value.bytesize, plain ? 1 : 0, quoted ? 1 : 0, style)
      end
    end

    def start_sequence(anchor, tag, implicit, style)
      anchor_pointer = LibYAML.cstring(anchor)
      tag_pointer = LibYAML.cstring(tag)
      __topaz_emit do |event|
        LibYAML.yaml_sequence_start_event_initialize(event, anchor_pointer, tag_pointer, implicit ? 1 : 0, style)
      end
    end

    def end_sequence
      __topaz_emit { |event| LibYAML.yaml_sequence_end_event_initialize(event) }
    end

    def start_mapping(anchor, tag, implicit, style)
      anchor_pointer = LibYAML.cstring(anchor)
      tag_pointer = LibYAML.cstring(tag)
      __topaz_emit do |event|
        LibYAML.yaml_mapping_start_event_initialize(event, anchor_pointer, tag_pointer, implicit ? 1 : 0, style)
      end
    end

    def end_mapping
      __topaz_emit { |event| LibYAML.yaml_mapping_end_event_initialize(event) }
    end

    def alias(anchor)
      anchor_pointer = LibYAML.cstring(anchor)
      __topaz_emit { |event| LibYAML.yaml_alias_event_initialize(event, anchor_pointer) }
    end

    private

    def __topaz_setup
      @emitter = FFI::MemoryPointer.new(:char, LibYAML::EMITTER_SIZE)
      @buffer = FFI::MemoryPointer.new(:char, BUFFER_SIZE)
      @written = FFI::MemoryPointer.new(:char, 8)
      raise NoMemoryError if LibYAML.yaml_emitter_initialize(@emitter) == 0
      LibYAML.yaml_emitter_set_output_string(@emitter, @buffer, BUFFER_SIZE, @written)
      LibYAML.yaml_emitter_set_unicode(@emitter, 1)
      LibYAML.yaml_emitter_set_indent(@emitter, @indentation)
      LibYAML.yaml_emitter_set_width(@emitter, @line_width)
      LibYAML.yaml_emitter_set_canonical(@emitter, @canonical ? 1 : 0)
    end

    def __topaz_emit
      raise RuntimeError, "uninitialized emitter" unless @emitter
      event = FFI::MemoryPointer.new(:char, LibYAML::EVENT_SIZE)
      raise NoMemoryError if yield(event) == 0
      if LibYAML.yaml_emitter_emit(@emitter, event) == 0
        raise RuntimeError, LibYAML.string_at(@emitter.get_pointer(LibYAML::EMITTER_PROBLEM)) || "emitter error"
      end
      __topaz_drain
      self
    end

    # Writes what libyaml has produced so far to the IO, and makes room for
    # more at the start of the buffer.
    def __topaz_drain
      n = @written.get_ulong(0)
      return if n == 0
      @io.write(@buffer.get_bytes(0, n))
      @written.put_ulong(0, 0)
    end
  end

  class ClassLoader
    private

    def path2class(path)
      path.to_s.split("::").inject(Object) do |mod, name|
        next mod if name.empty?
        unless mod.const_defined?(name, false) || mod.const_defined?(name)
          raise ArgumentError, "undefined class/module #{path}"
        end
        mod.const_get(name)
      end
    end
  end

  module Visitors
    class Visitor
    end

    class ToRuby < Visitor
      private

      # An exception with this message, without calling the class's own
      # initialize.
      def build_exception(klass, message)
        exception = klass.allocate
        Exception.instance_method(:initialize).bind(exception).call(message)
        exception
      end

      def init_struct(data, attrs)
        Struct.instance_method(:initialize).bind(data).call(*attrs)
        data
      end
    end

    class YAMLTree < Visitor
    end
  end
end
