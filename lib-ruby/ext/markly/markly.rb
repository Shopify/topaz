# The C half of markly (markly/markly.so) on libcmark-gfm and
# libcmark-gfm-extensions through FFI: Markly::Parser, Markly::Node and
# Markly.extensions. markly's Ruby files (flags, node, renderer) run
# unchanged on top. Found by name, through TOPAZ_LIBCMARK_GFM and
# TOPAZ_LIBCMARK_GFM_EXTENSIONS, or built from the gem's sources
# (Topaz::NativeLibrary). Nodes are never freed.
require "ffi"
require "topaz/native_library"

module Markly
  class Error < StandardError; end

  module LibCmark
    extend FFI::Library

    # Where there is no libcmark-gfm with its extensions (macOS ships the
    # parser alone), both are built from the gem's own copy of cmark-gfm.
    BUILD = lambda do
      Topaz::NativeLibrary.build("markly", "cmark-gfm", sources: %w[ext/markly/*.c], exclude: %w[ext/markly/markly.c],
                                 include: %w[ext/markly], flags: %w[-std=c99 -Wno-unknown-pragmas])
    end

    EXTENSIONS = Topaz::NativeLibrary.find("libcmark-gfm-extensions", env: "TOPAZ_LIBCMARK_GFM_EXTENSIONS",
                                           names: ["libcmark-gfm-extensions.so", "cmark-gfm-extensions"], build: BUILD)
    # The extensions register with the cmark-gfm they were built against,
    # so when they are topaz's build of the gem's sources, so is the parser.
    PARSER = if EXTENSIONS.start_with?(Topaz::NativeLibrary.cache_dir)
      EXTENSIONS
    else
      Topaz::NativeLibrary.find("libcmark-gfm", env: "TOPAZ_LIBCMARK_GFM", names: ["libcmark-gfm.so", "cmark-gfm"], build: BUILD)
    end
    ffi_lib PARSER

    [
      [:cmark_get_default_mem_allocator, [], :pointer],
      [:cmark_parser_new, [:int], :pointer],
      [:cmark_parser_feed, [:pointer, :pointer, :size_t], :void],
      [:cmark_parser_finish, [:pointer], :pointer],
      [:cmark_parser_attach_syntax_extension, [:pointer, :pointer], :int],
      [:cmark_find_syntax_extension, [:string], :pointer],
      [:cmark_node_new, [:int], :pointer],
      [:cmark_node_get_type, [:pointer], :int],
      [:cmark_node_get_type_string, [:pointer], :string],
      [:cmark_node_parent, [:pointer], :pointer],
      [:cmark_node_first_child, [:pointer], :pointer],
      [:cmark_node_last_child, [:pointer], :pointer],
      [:cmark_node_next, [:pointer], :pointer],
      [:cmark_node_previous, [:pointer], :pointer],
      [:cmark_node_get_literal, [:pointer], :pointer],
      [:cmark_node_set_literal, [:pointer, :pointer], :int],
      [:cmark_node_get_url, [:pointer], :pointer],
      [:cmark_node_set_url, [:pointer, :pointer], :int],
      [:cmark_node_get_title, [:pointer], :pointer],
      [:cmark_node_set_title, [:pointer, :pointer], :int],
      [:cmark_node_get_heading_level, [:pointer], :int],
      [:cmark_node_set_heading_level, [:pointer, :int], :int],
      [:cmark_node_get_list_type, [:pointer], :int],
      [:cmark_node_set_list_type, [:pointer, :int], :int],
      [:cmark_node_get_list_start, [:pointer], :int],
      [:cmark_node_set_list_start, [:pointer, :int], :int],
      [:cmark_node_get_list_tight, [:pointer], :int],
      [:cmark_node_set_list_tight, [:pointer, :int], :int],
      [:cmark_node_get_fence_info, [:pointer], :pointer],
      [:cmark_node_set_fence_info, [:pointer, :pointer], :int],
      [:cmark_node_get_start_line, [:pointer], :int],
      [:cmark_node_get_start_column, [:pointer], :int],
      [:cmark_node_get_end_line, [:pointer], :int],
      [:cmark_node_get_end_column, [:pointer], :int],
      [:cmark_node_unlink, [:pointer], :void],
      [:cmark_node_insert_before, [:pointer, :pointer], :int],
      [:cmark_node_insert_after, [:pointer, :pointer], :int],
      [:cmark_node_replace, [:pointer, :pointer], :int],
      [:cmark_node_prepend_child, [:pointer, :pointer], :int],
      [:cmark_node_append_child, [:pointer, :pointer], :int],
      [:cmark_llist_append, [:pointer, :pointer, :pointer], :pointer],
      [:cmark_llist_free, [:pointer, :pointer], :void],
      [:cmark_render_html, [:pointer, :int, :pointer], :pointer],
      [:cmark_render_commonmark, [:pointer, :int, :int], :pointer],
      [:cmark_render_plaintext, [:pointer, :int, :int], :pointer],
    ].each { |name, args, ret| attach_function name, args, ret }

    module Extensions
      extend FFI::Library
      ffi_lib LibCmark::EXTENSIONS
      attach_function :cmark_gfm_core_extensions_ensure_registered, [], :void
      attach_function :cmark_gfm_extensions_get_table_alignments, [:pointer], :pointer
      attach_function :cmark_gfm_extensions_get_table_columns, [:pointer], :uint16
      attach_function :cmark_gfm_extensions_get_tasklist_item_checked, [:pointer], :bool
      attach_function :cmark_gfm_extensions_set_tasklist_item_checked, [:pointer, :bool], :int
    end

    module LibC
      extend FFI::Library
      ffi_lib FFI::Library::LIBC
      attach_function :free, [:pointer], :void
    end

    Extensions.cmark_gfm_core_extensions_ensure_registered

    BLOCK = 0x8000
    INLINE = 0xc000
    TYPES = {
      document: BLOCK | 1, blockquote: BLOCK | 2, list: BLOCK | 3, list_item: BLOCK | 4,
      code_block: BLOCK | 5, html: BLOCK | 6, custom_block: BLOCK | 7, paragraph: BLOCK | 8,
      header: BLOCK | 9, hrule: BLOCK | 10, footnote_definition: BLOCK | 11,
      text: INLINE | 1, softbreak: INLINE | 2, linebreak: INLINE | 3, code: INLINE | 4,
      inline_html: INLINE | 5, custom_inline: INLINE | 6, emph: INLINE | 7, strong: INLINE | 8,
      link: INLINE | 9, image: INLINE | 10, footnote_reference: INLINE | 11,
    }.freeze
    NAMES = TYPES.invert.freeze

    NODES = {}

    def self.cstr(string)
      string = string.to_s
      memory = FFI::MemoryPointer.new(:char, string.bytesize + 1)
      memory.put_bytes(0, string, 0, string.bytesize) if string.bytesize > 0
      memory
    end

    def self.string_at(pointer)
      return nil if pointer.null?
      pointer.get_string(0).force_encoding(Encoding::UTF_8)
    end

    def self.take_string(pointer)
      string = string_at(pointer)
      LibC.free(pointer) unless pointer.null?
      string
    end

    # A cmark_llist of the named syntax extensions.
    def self.extension_list(names)
      raise TypeError, "wrong argument type #{names.class} (expected Array)" unless names.is_a?(Array)
      list = FFI::Pointer::NULL
      mem = cmark_get_default_mem_allocator
      names.each do |name|
        raise TypeError, "extension names should be Symbols; got a #{name.class}" unless name.is_a?(Symbol)
        extension = cmark_find_syntax_extension(name.to_s)
        if extension.null?
          cmark_llist_free(mem, list) unless list.null?
          raise ArgumentError, "extension #{name} not found\n"
        end
        list = cmark_llist_append(mem, list, extension)
      end
      [list, mem]
    end
  end

  def self.extensions
    %w[table strikethrough autolink tagfilter tasklist].select do |name|
      !LibCmark.cmark_find_syntax_extension(name).null?
    end
  end

  class Parser
    def initialize(flags)
      raise TypeError, "wrong argument type #{flags.class} (expected Integer)" unless flags.is_a?(Integer)
      @__topaz_ptr = LibCmark.cmark_parser_new(flags)
    end

    def enable(extension)
      raise TypeError, "wrong argument type #{extension.class} (expected Symbol)" unless extension.is_a?(Symbol)
      syntax = LibCmark.cmark_find_syntax_extension(extension.to_s)
      raise ArgumentError, "extension #{extension} not found" if syntax.null?
      LibCmark.cmark_parser_attach_syntax_extension(@__topaz_ptr, syntax)
      nil
    end

    def parse(text)
      text = Topaz.convert_type(text, String, :to_str)
      LibCmark.cmark_parser_feed(@__topaz_ptr, LibCmark.cstr(text), text.bytesize)
      Node.__wrap(LibCmark.cmark_parser_finish(@__topaz_ptr))
    end
  end

  class Node
    def self.__wrap(pointer)
      return nil if pointer.null?
      LibCmark::NODES[pointer.address] ||= begin
        node = allocate
        node.instance_variable_set(:@__topaz_ptr, pointer)
        node
      end
    end

    def self.new(type)
      raise TypeError, "wrong argument type #{type.class} (expected Symbol)" unless type.is_a?(Symbol)
      type = :custom_block if type == :custom
      code = LibCmark::TYPES[type] or raise Markly::Error, "invalid node of type #{type}"
      __wrap(LibCmark.cmark_node_new(code))
    end

    def __topaz_ptr
      @__topaz_ptr
    end

    def type
      code = LibCmark.cmark_node_get_type(@__topaz_ptr)
      LibCmark::NAMES[code] || LibCmark.cmark_node_get_type_string(@__topaz_ptr)&.to_sym ||
        raise(Markly::Error, "invalid node type #{code}")
    end

    def type_string
      LibCmark.cmark_node_get_type_string(@__topaz_ptr)
    end

    def source_position
      {
        start_line: LibCmark.cmark_node_get_start_line(@__topaz_ptr),
        start_column: LibCmark.cmark_node_get_start_column(@__topaz_ptr),
        end_line: LibCmark.cmark_node_get_end_line(@__topaz_ptr),
        end_column: LibCmark.cmark_node_get_end_column(@__topaz_ptr),
      }
    end

    def string_content
      literal = LibCmark.cmark_node_get_literal(@__topaz_ptr)
      raise Markly::Error, "could not get string content" if literal.null?
      LibCmark.string_at(literal)
    end

    def string_content=(string)
      string = Topaz.convert_type(string, String, :to_str)
      if LibCmark.cmark_node_set_literal(@__topaz_ptr, LibCmark.cstr(string)) == 0
        raise Markly::Error, "could not set string content"
      end
      string
    end

    def delete
      LibCmark.cmark_node_unlink(@__topaz_ptr)
      nil
    end

    %i[first_child last_child next previous parent].each do |name|
      function = :"cmark_node_#{name}"
      define_method(name) { Node.__wrap(LibCmark.__send__(function, @__topaz_ptr)) }
    end

    {
      insert_before: "could not insert before", insert_after: "could not insert after",
      replace: "could not replace", prepend_child: "could not prepend child",
      append_child: "could not append child",
    }.each do |name, message|
      define_method(name) do |other|
        raise TypeError, "wrong argument type #{other.class} (expected Markly::Node)" unless other.is_a?(Node)
        raise Markly::Error, message if LibCmark.__send__(:"cmark_node_#{name}", @__topaz_ptr, other.__topaz_ptr) == 0
        true
      end
    end

    {
      url: ["cmark_node_get_url", "cmark_node_set_url", "url"],
      title: ["cmark_node_get_title", "cmark_node_set_title", "title"],
      fence_info: ["cmark_node_get_fence_info", "cmark_node_set_fence_info", "fence info"],
    }.each do |name, (getter, setter, what)|
      define_method(name) do
        value = LibCmark.__send__(getter, @__topaz_ptr)
        raise Markly::Error, "could not get #{what}" if value.null?
        LibCmark.string_at(value)
      end
      define_method(:"#{name}=") do |value|
        value = Topaz.convert_type(value, String, :to_str)
        raise Markly::Error, "could not set #{what}" if LibCmark.__send__(setter, @__topaz_ptr, LibCmark.cstr(value)) == 0
        value
      end
    end

    def header_level
      level = LibCmark.cmark_node_get_heading_level(@__topaz_ptr)
      raise Markly::Error, "could not get header_level" if level == 0
      level
    end

    def header_level=(level)
      raise Markly::Error, "could not set header_level" if LibCmark.cmark_node_set_heading_level(@__topaz_ptr, Integer(level)) == 0
      level
    end

    def list_type
      case LibCmark.cmark_node_get_list_type(@__topaz_ptr)
      when 1 then :bullet_list
      when 2 then :ordered_list
      else raise Markly::Error, "could not get list_type"
      end
    end

    def list_type=(type)
      code = { bullet_list: 1, ordered_list: 2 }.fetch(type) { raise Markly::Error, "invalid list_type" }
      raise Markly::Error, "could not set list_type" if LibCmark.cmark_node_set_list_type(@__topaz_ptr, code) == 0
      type
    end

    def list_start
      raise Markly::Error, "can't get list_start for non-ordered list #{list_type}" unless list_type == :ordered_list
      LibCmark.cmark_node_get_list_start(@__topaz_ptr)
    end

    def list_start=(start)
      raise Markly::Error, "could not set list_start" if LibCmark.cmark_node_set_list_start(@__topaz_ptr, Integer(start)) == 0
      start
    end

    def list_tight
      raise Markly::Error, "can't get list_tight for non-list #{type}" unless type == :list
      LibCmark.cmark_node_get_list_tight(@__topaz_ptr) != 0
    end

    def list_tight=(tight)
      raise Markly::Error, "could not set list_tight" if LibCmark.cmark_node_set_list_tight(@__topaz_ptr, tight ? 1 : 0) == 0
      tight
    end

    def table_alignments
      alignments = LibCmark::Extensions.cmark_gfm_extensions_get_table_alignments(@__topaz_ptr)
      columns = LibCmark::Extensions.cmark_gfm_extensions_get_table_columns(@__topaz_ptr)
      return [] if alignments.null?
      Array.new(columns) do |i|
        case alignments.get_uint8(i).chr
        when "l" then :left
        when "r" then :right
        when "c" then :center
        end
      end
    end

    def tasklist_item_checked?
      LibCmark::Extensions.cmark_gfm_extensions_get_tasklist_item_checked(@__topaz_ptr)
    end

    def tasklist_item_checked=(checked)
      LibCmark::Extensions.cmark_gfm_extensions_set_tasklist_item_checked(@__topaz_ptr, checked ? true : false)
      checked
    end

    def parent_footnote_def
      nil
    end

    def html_escape_href(string)
      string.to_s.gsub(/[^A-Za-z0-9\-._~:\/?#\[\]@!$()*+,;=%&']/) { |c| c.bytes.map { |b| "%%%02X" % b }.join }
                 .gsub("&", "&amp;").gsub("'", "&#x27;")
    end

    def html_escape_html(string)
      string.to_s.gsub(/[&<>"]/, "&" => "&amp;", "<" => "&lt;", ">" => "&gt;", '"' => "&quot;")
    end

    private

    def _render_html(options, extensions)
      raise TypeError, "wrong argument type #{options.class} (expected Integer)" unless options.is_a?(Integer)
      list, mem = LibCmark.extension_list(extensions)
      html = LibCmark.take_string(LibCmark.cmark_render_html(@__topaz_ptr, options, list))
      LibCmark.cmark_llist_free(mem, list) unless list.null?
      html
    end

    def _render_commonmark(options, width = 120)
      LibCmark.take_string(LibCmark.cmark_render_commonmark(@__topaz_ptr, Integer(options), Integer(width)))
    end

    def _render_plaintext(options, width = 120)
      LibCmark.take_string(LibCmark.cmark_render_plaintext(@__topaz_ptr, Integer(options), Integer(width)))
    end
  end
end
