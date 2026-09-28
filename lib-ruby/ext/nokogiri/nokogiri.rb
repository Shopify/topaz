# The C half of Nokogiri (nokogiri/nokogiri.so) on libxml2 through FFI.
# Nokogiri's Ruby files run unchanged on top.
#
# Supported: XML and HTML4 parsing, documents, nodes of every kind,
# attributes, namespaces, node sets, fragments parsed in context, XPath
# (Nokogiri's builtin CSS helper functions are rewritten into plain
# XPath), serialization, entity lookup and element descriptions.
# Not supported yet (they need FFI callbacks, or are not bound): parse
# error lists, XPath functions written in Ruby, SAX, Reader, XSLT,
# schema and RelaxNG validation, and HTML5 (gumbo).
#
# Struct offsets are libxml2's on 64-bit Linux. Nodes are never freed.
require "ffi"
require "stringio"

module Nokogiri
  module LibXML
    extend FFI::Library

    candidates = [ENV["TOPAZ_LIBXML2"], "libxml2.so.16", "libxml2.so.2", "libxml2.so", "xml2"].compact
    loaded = false
    candidates.each do |name|
      begin
        ffi_lib name
        loaded = true
        break
      rescue LoadError
      end
    end
    raise LoadError, "cannot load libxml2 (set TOPAZ_LIBXML2 to its path)" unless loaded

    functions = [
      [:htmlReadMemory, [:pointer, :int, :string, :string, :int], :pointer],
      [:xmlReadMemory, [:pointer, :int, :string, :string, :int], :pointer],
      [:htmlNewDoc, [:string, :string], :pointer],
      [:htmlNewDocNoDtD, [:string, :string], :pointer],
      [:xmlNewDoc, [:string], :pointer],
      [:xmlCopyDoc, [:pointer, :int], :pointer],
      [:xmlDocGetRootElement, [:pointer], :pointer],
      [:xmlDocSetRootElement, [:pointer, :pointer], :pointer],
      [:xmlNewDocNode, [:pointer, :pointer, :string, :pointer], :pointer],
      [:xmlNewDocText, [:pointer, :pointer], :pointer],
      [:xmlNewDocComment, [:pointer, :pointer], :pointer],
      [:xmlNewCDataBlock, [:pointer, :pointer, :int], :pointer],
      [:xmlNewDocPI, [:pointer, :string, :pointer], :pointer],
      [:xmlNewReference, [:pointer, :string], :pointer],
      [:xmlNewDocProp, [:pointer, :string, :pointer], :pointer],
      [:xmlNewDocFragment, [:pointer], :pointer],
      [:xmlDocCopyNode, [:pointer, :pointer, :int], :pointer],
      [:xmlUnlinkNode, [:pointer], :void],
      [:xmlAddChild, [:pointer, :pointer], :pointer],
      [:xmlAddNextSibling, [:pointer, :pointer], :pointer],
      [:xmlAddPrevSibling, [:pointer, :pointer], :pointer],
      [:xmlReplaceNode, [:pointer, :pointer], :pointer],
      [:xmlNodeGetContent, [:pointer], :pointer],
      [:xmlNodeSetContent, [:pointer, :pointer], :int],
      [:xmlNodeAddContentLen, [:pointer, :pointer, :int], :int],
      [:xmlNodeSetName, [:pointer, :string], :void],
      [:xmlGetNoNsProp, [:pointer, :string], :pointer],
      [:xmlGetProp, [:pointer, :string], :pointer],
      [:xmlGetNsProp, [:pointer, :string, :pointer], :pointer],
      [:xmlHasProp, [:pointer, :string], :pointer],
      [:xmlHasNsProp, [:pointer, :string, :string], :pointer],
      [:xmlSetProp, [:pointer, :string, :pointer], :pointer],
      [:xmlSetNsProp, [:pointer, :pointer, :string, :pointer], :pointer],
      [:xmlSearchNs, [:pointer, :pointer, :string], :pointer],
      [:xmlSearchNsByHref, [:pointer, :pointer, :string], :pointer],
      [:xmlNewNs, [:pointer, :string, :string], :pointer],
      [:xmlSetNs, [:pointer, :pointer], :void],
      [:xmlGetNsList, [:pointer, :pointer], :pointer],
      [:xmlIsBlankNode, [:pointer], :int],
      [:xmlGetNodePath, [:pointer], :pointer],
      [:xmlGetLineNo, [:pointer], :long],
      [:xmlNodeGetLang, [:pointer], :pointer],
      [:xmlNodeSetLang, [:pointer, :string], :void],
      [:xmlEncodeSpecialChars, [:pointer, :pointer], :pointer],
      [:xmlEncodeEntitiesReentrant, [:pointer, :pointer], :pointer],
      [:xmlStrdup, [:pointer], :pointer],
      [:xmlBufferCreate, [], :pointer],
      [:xmlBufferFree, [:pointer], :void],
      [:xmlBufferContent, [:pointer], :pointer],
      [:xmlBufferLength, [:pointer], :int],
      [:xmlSaveToBuffer, [:pointer, :string, :int], :pointer],
      [:xmlSaveTree, [:pointer, :pointer], :long],
      [:xmlSaveClose, [:pointer], :int],
      [:htmlNodeDump, [:pointer, :pointer, :pointer], :int],
      [:xmlXPathNewContext, [:pointer], :pointer],
      [:xmlXPathFreeContext, [:pointer], :void],
      [:xmlXPathEvalExpression, [:pointer, :pointer], :pointer],
      [:xmlXPathFreeObject, [:pointer], :void],
      [:xmlXPathFreeNodeSetList, [:pointer], :void],
      [:xmlXPathRegisterNs, [:pointer, :string, :string], :int],
      [:xmlXPathRegisterVariable, [:pointer, :string, :pointer], :int],
      [:xmlXPathNewString, [:pointer], :pointer],
      [:xmlXPathNewFloat, [:double], :pointer],
      [:xmlXPathNewBoolean, [:int], :pointer],
      [:xmlXPathCmpNodes, [:pointer, :pointer], :int],
      [:xmlParseInNodeContext, [:pointer, :pointer, :int, :int, :pointer], :int],
      [:xmlResetLastError, [], :void],
      [:xmlGetLastError, [], :pointer],
      [:xmlCreateIntSubset, [:pointer, :string, :string, :string], :pointer],
      [:xmlNewDtd, [:pointer, :string, :string, :string], :pointer],
      [:xmlAddDocEntity, [:pointer, :string, :int, :string, :string, :string], :pointer],
      [:xmlFindCharEncodingHandler, [:string], :pointer],
      [:xmlAddEncodingAlias, [:string, :string], :int],
      [:xmlDelEncodingAlias, [:string], :int],
      [:xmlCleanupEncodingAliases, [], :void],
      [:htmlTagLookup, [:string], :pointer],
      [:htmlEntityLookup, [:string], :pointer],
      [:xmlXIncludeProcessTreeFlags, [:pointer, :int], :int],
    ]
    functions.each { |name, args, ret| attach_function name, args, ret }

    # libxml2 allocates with malloc, so its strings are freed with free.
    module LibC
      extend FFI::Library
      ffi_lib FFI::Library::LIBC
      attach_function :free, [:pointer], :void
    end

    # xmlNode (and the fields every node struct starts with)
    PRIVATE = 0
    TYPE = 8
    NAME = 16
    CHILDREN = 24
    LAST = 32
    PARENT = 40
    NEXT = 48
    PREV = 56
    DOC = 64
    NS = 72
    CONTENT = 80
    PROPERTIES = 88
    NS_DEF = 96
    LINE = 112
    # xmlDoc
    DOC_INT_SUBSET = 80
    DOC_EXT_SUBSET = 88
    DOC_VERSION = 104
    DOC_ENCODING = 112
    DOC_URL = 136
    # xmlNs
    NS_NEXT = 0
    NS_HREF = 16
    NS_PREFIX = 24
    # xmlDtd
    DTD_EXTERNAL_ID = 104
    DTD_SYSTEM_ID = 112
    # xmlXPathContext
    XPATH_CONTEXT_NODE = 8
    # xmlXPathObject
    XPATH_TYPE = 0
    XPATH_NODESET = 8
    XPATH_BOOLVAL = 16
    XPATH_FLOATVAL = 24
    XPATH_STRINGVAL = 32
    # xmlError
    ERROR_DOMAIN = 0
    ERROR_CODE = 4
    ERROR_MESSAGE = 8
    ERROR_LEVEL = 16
    ERROR_FILE = 24
    ERROR_LINE = 32
    ERROR_STR1 = 40
    ERROR_STR2 = 48
    ERROR_STR3 = 56
    ERROR_INT1 = 64
    ERROR_INT2 = 68

    ELEMENT_NODE = 1
    ATTRIBUTE_NODE = 2
    TEXT_NODE = 3
    CDATA_SECTION_NODE = 4
    ENTITY_REF_NODE = 5
    PI_NODE = 7
    COMMENT_NODE = 8
    DOCUMENT_NODE = 9
    DOCUMENT_FRAG_NODE = 11
    HTML_DOCUMENT_NODE = 13
    DTD_NODE = 14
    ELEMENT_DECL = 15
    ATTRIBUTE_DECL = 16
    ENTITY_DECL = 17
    NAMESPACE_DECL = 18

    PARSE_RECOVER = 1

    # A NUL-terminated copy of a Ruby string.
    def self.cstr(string)
      string = string.to_s
      memory = FFI::MemoryPointer.new(:char, string.bytesize + 1)
      memory.put_bytes(0, string, 0, string.bytesize) if string.bytesize > 0
      memory
    end

    def self.string_at(pointer)
      return nil if pointer.nil? || pointer.null?
      pointer.get_string(0).force_encoding(Encoding::UTF_8)
    end

    # A string libxml2 allocated, which is freed after reading it.
    def self.take_string(pointer)
      return nil if pointer.null?
      string = string_at(pointer)
      LibC.free(pointer)
      string
    end

    def self.null?(pointer)
      pointer.nil? || pointer.null?
    end

    # The last error libxml2 recorded, as a Nokogiri::XML::SyntaxError.
    def self.last_error(klass = Nokogiri::XML::SyntaxError)
      error = xmlGetLastError()
      return nil if error.null?
      message = string_at(error.get_pointer(ERROR_MESSAGE)) || "unknown error"
      syntax_error = klass.new(message.chomp)
      syntax_error.instance_variable_set(:@domain, error.get_int32(ERROR_DOMAIN))
      syntax_error.instance_variable_set(:@code, error.get_int32(ERROR_CODE))
      syntax_error.instance_variable_set(:@level, error.get_int32(ERROR_LEVEL))
      syntax_error.instance_variable_set(:@file, string_at(error.get_pointer(ERROR_FILE)))
      syntax_error.instance_variable_set(:@line, error.get_int32(ERROR_LINE))
      syntax_error.instance_variable_set(:@str1, string_at(error.get_pointer(ERROR_STR1)))
      syntax_error.instance_variable_set(:@str2, string_at(error.get_pointer(ERROR_STR2)))
      syntax_error.instance_variable_set(:@str3, string_at(error.get_pointer(ERROR_STR3)))
      syntax_error.instance_variable_set(:@int1, error.get_int32(ERROR_INT1))
      syntax_error.instance_variable_set(:@column, error.get_int32(ERROR_INT2))
      syntax_error
    end

    # Ruby objects for libxml2 documents, by address.
    DOCUMENTS = {}

    def self.parser_version
      library = ffi_libraries.first
      variable = library.respond_to?(:find_variable) ? library.find_variable("xmlParserVersion") : nil
      if variable && !variable.null?
        pointer = FFI::Pointer.new(variable.address).get_pointer(0)
        digits = pointer.null? ? nil : pointer.get_string(0)
        if digits && digits =~ /\A(\d)(\d\d)(\d\d)/
          return "#{$1.to_i}.#{$2.to_i}.#{$3.to_i}"
        end
      end
      "2.0.0"
    rescue StandardError
      "2.0.0"
    end
  end

  LIBXML_COMPILED_VERSION = LibXML.parser_version
  # As libxml2's xmlParserVersion: 2.15.4 is "21504".
  LIBXML_LOADED_VERSION = LIBXML_COMPILED_VERSION.split(".").then { |a, b, c| "#{a}#{b.rjust(2, "0")}#{c.rjust(2, "0")}" }
  # libxslt is not bound.
  LIBXSLT_COMPILED_VERSION = "0.0.0"
  LIBXSLT_LOADED_VERSION = "00000"
  LIBXML_ZLIB_ENABLED = false
  LIBXML_ICONV_ENABLED = true
  LIBXSLT_DATETIME_ENABLED = false
  PACKAGED_LIBRARIES = false
  PRECOMPILED_LIBRARIES = false
  LIBXML2_PATCHES = nil
  LIBXSLT_PATCHES = nil
  LIBXML_MEMORY_MANAGEMENT = "default"

  class SyntaxError < ::StandardError; end

  module Gumbo
    DEFAULT_MAX_ATTRIBUTES = 400
    DEFAULT_MAX_ERRORS = 0
    DEFAULT_MAX_TREE_DEPTH = 400

    def self.parse(*)
      raise NotImplementedError, "HTML5 parsing (gumbo) is not supported by topaz's Nokogiri"
    end

    def self.fragment(*)
      raise NotImplementedError, "HTML5 parsing (gumbo) is not supported by topaz's Nokogiri"
    end
  end

  module HTML4
    module SAX; end
  end

  module HTML5; end

  module XSLT
    class Stylesheet
      def self.parse_stylesheet_doc(*)
        raise NotImplementedError, "XSLT is not supported by topaz's Nokogiri"
      end
    end

    def self.register(*)
      raise NotImplementedError, "XSLT is not supported by topaz's Nokogiri"
    end
  end

  module XML
    class SyntaxError < ::Nokogiri::SyntaxError; end

    module XPath
      class SyntaxError < XML::SyntaxError; end
    end

    module SAX
      class Parser; end

      class ParserContext
        def self.native_memory(*)
          raise NotImplementedError, "SAX parsing is not supported by topaz's Nokogiri"
        end

        def self.native_io(*)
          native_memory
        end

        def self.native_file(*)
          native_memory
        end
      end

      class PushParser
        private

        def initialize_native(*)
          raise NotImplementedError, "SAX parsing is not supported by topaz's Nokogiri"
        end
      end
    end

    class Reader
      def self.from_memory(*)
        raise NotImplementedError, "XML::Reader is not supported by topaz's Nokogiri"
      end

      def self.from_io(*)
        from_memory
      end
    end

    class Schema
      def self.from_document(*)
        raise NotImplementedError, "XML::Schema is not supported by topaz's Nokogiri"
      end
    end

    class RelaxNG < Schema; end

    class ElementContent; end

    class Namespace
      attr_reader :document

      def self.__wrap(pointer, document)
        cache = document.instance_variable_get(:@__topaz_namespaces)
        cache = document.instance_variable_set(:@__topaz_namespaces, {}) if cache.nil?
        address = pointer.address
        cache[address] ||= begin
          namespace = allocate
          namespace.instance_variable_set(:@__topaz_ptr, pointer)
          namespace.instance_variable_set(:@document, document)
          document.decorate(namespace)
          namespace
        end
      end

      def __topaz_ptr
        @__topaz_ptr
      end

      def prefix
        LibXML.string_at(@__topaz_ptr.get_pointer(LibXML::NS_PREFIX))
      end

      def href
        LibXML.string_at(@__topaz_ptr.get_pointer(LibXML::NS_HREF))
      end
    end

    class Node
      # The Ruby object for a libxml2 node, made once per node.
      def self.__wrap(pointer, klass = nil)
        return nil if LibXML.null?(pointer)
        type = pointer.get_int32(LibXML::TYPE)
        if type == LibXML::DOCUMENT_NODE || type == LibXML::HTML_DOCUMENT_NODE
          return Document.__wrap(pointer)
        end
        document = Document.__wrap(pointer.get_pointer(LibXML::DOC))
        cache = document.__topaz_nodes
        address = pointer.address
        node = cache[address]
        return node if node
        klass ||= case type
                  when LibXML::ELEMENT_NODE then Element
                  when LibXML::TEXT_NODE then Text
                  when LibXML::ATTRIBUTE_NODE then Attr
                  when LibXML::ENTITY_REF_NODE then EntityReference
                  when LibXML::COMMENT_NODE then Comment
                  when LibXML::DOCUMENT_FRAG_NODE then DocumentFragment
                  when LibXML::PI_NODE then ProcessingInstruction
                  when LibXML::ENTITY_DECL then EntityDecl
                  when LibXML::CDATA_SECTION_NODE then CDATA
                  when LibXML::DTD_NODE then DTD
                  when LibXML::ATTRIBUTE_DECL then AttributeDecl
                  when LibXML::ELEMENT_DECL then ElementDecl
                  else Node
                  end
        node = klass.allocate
        node.instance_variable_set(:@__topaz_ptr, pointer)
        cache[address] = node
        document.decorate(node)
        node
      end

      def self.__document_ptr(document)
        document = document.document if document.is_a?(Node) && !document.is_a?(Document)
        raise ArgumentError, "document must be a Nokogiri::XML::Document" unless document.is_a?(Document)
        document.__topaz_ptr
      end

      # Node.new(name, document) and the like: the node is made, then
      # initialize runs with the arguments, then the block.
      def self.__finish_new(node, args, &block)
        node.__send__(:initialize, *args)
        yield node if block
        node
      end

      def self.new(name, document, *rest, &block)
        doc = __document_ptr(document)
        pointer = LibXML.xmlNewDocNode(doc, FFI::Pointer::NULL, name.to_s, FFI::Pointer::NULL)
        __finish_new(__wrap(pointer, self), [name, document, *rest], &block)
      end

      def __topaz_ptr
        @__topaz_ptr
      end

      def __topaz_replace_ptr(pointer)
        old = @__topaz_ptr
        document.__topaz_nodes.delete(old.address) if old
        @__topaz_ptr = pointer
        document.__topaz_nodes[pointer.address] = self
      end

      def document
        Document.__wrap(@__topaz_ptr.get_pointer(LibXML::DOC))
      end

      def pointer_id
        @__topaz_ptr.address
      end

      def data_ptr?
        !@__topaz_ptr.nil?
      end

      def node_type
        @__topaz_ptr.get_int32(LibXML::TYPE)
      end
      alias type node_type

      def node_name
        LibXML.string_at(@__topaz_ptr.get_pointer(LibXML::NAME))
      end

      def node_name=(name)
        LibXML.xmlNodeSetName(@__topaz_ptr, name.to_s)
      end

      def parent
        Node.__wrap(@__topaz_ptr.get_pointer(LibXML::PARENT))
      end

      def child
        Node.__wrap(@__topaz_ptr.get_pointer(LibXML::CHILDREN))
      end

      def next_sibling
        Node.__wrap(@__topaz_ptr.get_pointer(LibXML::NEXT))
      end

      def previous_sibling
        Node.__wrap(@__topaz_ptr.get_pointer(LibXML::PREV))
      end

      def __topaz_children_pointers
        pointers = []
        child = @__topaz_ptr.get_pointer(LibXML::CHILDREN)
        until child.null?
          pointers << child
          child = child.get_pointer(LibXML::NEXT)
        end
        pointers
      end

      def children
        NodeSet.__from(document, __topaz_children_pointers.map { |p| Node.__wrap(p) })
      end

      def element_children
        NodeSet.__from(document, __topaz_children_pointers.select { |p| p.get_int32(LibXML::TYPE) == LibXML::ELEMENT_NODE }.map { |p| Node.__wrap(p) })
      end

      def first_element_child
        pointer = __topaz_children_pointers.find { |p| p.get_int32(LibXML::TYPE) == LibXML::ELEMENT_NODE }
        pointer && Node.__wrap(pointer)
      end

      def last_element_child
        pointer = __topaz_children_pointers.reverse.find { |p| p.get_int32(LibXML::TYPE) == LibXML::ELEMENT_NODE }
        pointer && Node.__wrap(pointer)
      end

      def next_element
        sibling = @__topaz_ptr.get_pointer(LibXML::NEXT)
        sibling = sibling.get_pointer(LibXML::NEXT) while !sibling.null? && sibling.get_int32(LibXML::TYPE) != LibXML::ELEMENT_NODE
        Node.__wrap(sibling)
      end

      def previous_element
        sibling = @__topaz_ptr.get_pointer(LibXML::PREV)
        sibling = sibling.get_pointer(LibXML::PREV) while !sibling.null? && sibling.get_int32(LibXML::TYPE) != LibXML::ELEMENT_NODE
        Node.__wrap(sibling)
      end

      def content
        LibXML.take_string(LibXML.xmlNodeGetContent(@__topaz_ptr))
      end

      def blank?
        LibXML.xmlIsBlankNode(@__topaz_ptr) == 1
      end

      def path
        LibXML.take_string(LibXML.xmlGetNodePath(@__topaz_ptr))
      end

      def line
        LibXML.xmlGetLineNo(@__topaz_ptr)
      end

      def line=(number)
        @__topaz_ptr.put_uint16(LibXML::LINE, [Integer(number), 65535].min)
        number
      end

      def lang
        LibXML.take_string(LibXML.xmlNodeGetLang(@__topaz_ptr))
      end

      def lang=(lang)
        LibXML.xmlNodeSetLang(@__topaz_ptr, lang.to_s)
        lang
      end

      def key?(attribute)
        !LibXML.null?(LibXML.xmlHasProp(@__topaz_ptr, attribute.to_s))
      end

      def namespaced_key?(attribute, namespace)
        !LibXML.null?(LibXML.xmlHasNsProp(@__topaz_ptr, attribute.to_s, namespace.nil? ? nil : namespace.to_s))
      end

      def attribute(name)
        Node.__wrap(LibXML.xmlHasProp(@__topaz_ptr, name.to_s))
      end

      def attribute_with_ns(name, namespace)
        Node.__wrap(LibXML.xmlHasNsProp(@__topaz_ptr, name.to_s, namespace.nil? ? nil : namespace.to_s))
      end

      def attribute_nodes
        return [] unless node_type == LibXML::ELEMENT_NODE
        attributes = []
        property = @__topaz_ptr.get_pointer(LibXML::PROPERTIES)
        until property.null?
          attributes << Node.__wrap(property)
          property = property.get_pointer(LibXML::NEXT)
        end
        attributes
      end

      def namespace
        type = node_type
        return nil unless type == LibXML::ELEMENT_NODE || type == LibXML::ATTRIBUTE_NODE
        pointer = @__topaz_ptr.get_pointer(LibXML::NS)
        pointer.null? ? nil : Namespace.__wrap(pointer, document)
      end

      def namespace_definitions
        return [] unless node_type == LibXML::ELEMENT_NODE
        definitions = []
        ns = @__topaz_ptr.get_pointer(LibXML::NS_DEF)
        until ns.null?
          definitions << Namespace.__wrap(ns, document)
          ns = ns.get_pointer(LibXML::NS_NEXT)
        end
        definitions
      end

      def namespace_scopes
        list = LibXML.xmlGetNsList(document.__topaz_ptr, @__topaz_ptr)
        return [] if list.null?
        scopes = []
        i = 0
        until (ns = list.get_pointer(i * 8)).null?
          scopes << Namespace.__wrap(ns, document)
          i += 1
        end
        LibXML::LibC.free(list)
        scopes
      end

      def add_namespace_definition(prefix, href)
        ns = LibXML.xmlSearchNs(document.__topaz_ptr, @__topaz_ptr, prefix.nil? ? nil : prefix.to_s)
        if ns.null? || LibXML.string_at(ns.get_pointer(LibXML::NS_HREF)) != href.to_s
          ns = LibXML.xmlNewNs(@__topaz_ptr, href.to_s, prefix.nil? ? nil : prefix.to_s)
        end
        return nil if ns.null?
        LibXML.xmlSetNs(@__topaz_ptr, ns) if prefix.nil? || @__topaz_ptr.get_pointer(LibXML::NS).null? && false
        Namespace.__wrap(ns, document)
      end

      def encode_special_chars(string)
        LibXML.take_string(LibXML.xmlEncodeSpecialChars(document.__topaz_ptr, LibXML.cstr(string)))
      end

      def internal_subset
        Node.__wrap(document.__topaz_ptr.get_pointer(LibXML::DOC_INT_SUBSET))
      end

      def external_subset
        Node.__wrap(document.__topaz_ptr.get_pointer(LibXML::DOC_EXT_SUBSET))
      end

      def create_internal_subset(name, external_id, system_id)
        Node.__wrap(LibXML.xmlCreateIntSubset(document.__topaz_ptr, name&.to_s, external_id&.to_s, system_id&.to_s))
      end

      def create_external_subset(name, external_id, system_id)
        Node.__wrap(LibXML.xmlNewDtd(document.__topaz_ptr, name&.to_s, external_id&.to_s, system_id&.to_s))
      end

      def unlink
        LibXML.xmlUnlinkNode(@__topaz_ptr)
        self
      end

      # The content is taken as XML text: Node#content= escapes it first.
      def native_content=(content)
        LibXML.xmlNodeSetContent(@__topaz_ptr, LibXML.cstr(content.to_s))
        content
      end

      protected

      def protected_initialize_copy_with_args(other, level, new_parent_doc)
        copy = LibXML.xmlDocCopyNode(other.__topaz_ptr, new_parent_doc.__topaz_ptr, level)
        raise RuntimeError, "could not copy node" if copy.null?
        @__topaz_ptr = copy
        new_parent_doc.__topaz_nodes[copy.address] = self
        self
      end

      private

      def get(attribute)
        return nil if attribute.nil?
        name = attribute.to_s
        value = if (colon = name.index(":"))
                  prefix = name[0, colon]
                  local = name[colon + 1..]
                  ns = LibXML.xmlSearchNs(document.__topaz_ptr, @__topaz_ptr, prefix)
                  if ns.null?
                    LibXML.xmlGetProp(@__topaz_ptr, name)
                  else
                    LibXML.xmlGetNsProp(@__topaz_ptr, local, ns.get_pointer(LibXML::NS_HREF))
                  end
                else
                  LibXML.xmlGetNoNsProp(@__topaz_ptr, name)
                end
        LibXML.take_string(value)
      end

      def set(name, value)
        return nil unless node_type == LibXML::ELEMENT_NODE
        LibXML.xmlSetProp(@__topaz_ptr, name.to_s, value.nil? ? FFI::Pointer::NULL : LibXML.cstr(value.to_s))
        value
      end

      def set_namespace(namespace)
        LibXML.xmlSetNs(@__topaz_ptr, namespace.nil? ? FFI::Pointer::NULL : namespace.__topaz_ptr)
        self
      end

      # Moves (or, from another document, copies) reparentee into place.
      def __topaz_reparent(reparentee, how)
        unless reparentee.is_a?(Node)
          raise ArgumentError, "node must be a Nokogiri::XML::Node or Nokogiri::XML::Namespace"
        end
        if reparentee.is_a?(Document)
          raise ArgumentError, "cannot reparent #{reparentee.class} there"
        end
        pointer = reparentee.__topaz_ptr
        my_doc = @__topaz_ptr.get_pointer(LibXML::DOC)
        if pointer.get_pointer(LibXML::DOC).address != my_doc.address
          copy = LibXML.xmlDocCopyNode(pointer, my_doc, 1)
          raise RuntimeError, "could not reparent node (xmlDocCopyNode)" if copy.null?
          LibXML.xmlUnlinkNode(pointer)
          reparentee.instance_variable_set(:@__topaz_ptr, copy)
          document.__topaz_nodes[copy.address] = reparentee
          pointer = copy
        else
          LibXML.xmlUnlinkNode(pointer)
        end
        result = case how
                 when :child then LibXML.xmlAddChild(@__topaz_ptr, pointer)
                 when :next then LibXML.xmlAddNextSibling(@__topaz_ptr, pointer)
                 when :previous then LibXML.xmlAddPrevSibling(@__topaz_ptr, pointer)
                 when :replace then (LibXML.xmlReplaceNode(@__topaz_ptr, pointer); pointer)
                 end
        raise RuntimeError, "could not reparent node" if result.null?
        if result.address != pointer.address
          # libxml2 merged a text node into its neighbour.
          reparentee.instance_variable_set(:@__topaz_ptr, result)
          document.__topaz_nodes[result.address] = reparentee
        end
        reparentee.decorate! if reparentee.respond_to?(:decorate!)
        reparentee
      end

      def add_child_node(child)
        __topaz_reparent(child, :child)
      end

      def add_next_sibling_node(sibling)
        __topaz_reparent(sibling, :next)
      end

      def add_previous_sibling_node(sibling)
        __topaz_reparent(sibling, :previous)
      end

      def replace_node(node)
        __topaz_reparent(node, :replace)
      end

      def compare(other)
        LibXML.xmlXPathCmpNodes(other.__topaz_ptr, @__topaz_ptr)
      end

      def dump_html
        buffer = LibXML.xmlBufferCreate
        LibXML.htmlNodeDump(buffer, document.__topaz_ptr, @__topaz_ptr)
        html = LibXML.string_at(LibXML.xmlBufferContent(buffer)) || ""
        LibXML.xmlBufferFree(buffer)
        html
      end

      def native_write_to(io, encoding, indent_string, options)
        buffer = LibXML.xmlBufferCreate
        save = LibXML.xmlSaveToBuffer(buffer, encoding.nil? ? nil : encoding.to_s, Integer(options))
        LibXML.xmlSaveTree(save, @__topaz_ptr)
        LibXML.xmlSaveClose(save)
        length = LibXML.xmlBufferLength(buffer)
        data = length == 0 ? "".b : LibXML.xmlBufferContent(buffer).get_bytes(0, length)
        LibXML.xmlBufferFree(buffer)
        io.write(data)
        io
      end

      def prepend_newline?
        false
      end

      def html_standard_serialize(*)
        raise NotImplementedError, "HTML5 serialization is not supported by topaz's Nokogiri"
      end

      def process_xincludes(options)
        LibXML.xmlXIncludeProcessTreeFlags(@__topaz_ptr, Integer(options))
        self
      end

      def in_context(string, options)
        string = string.to_s
        list = FFI::MemoryPointer.new(:pointer, 1)
        LibXML.xmlResetLastError
        status = LibXML.xmlParseInNodeContext(@__topaz_ptr, LibXML.cstr(string), string.bytesize,
                                               Integer(options), list)
        nodes = []
        child = list.get_pointer(0)
        # Unlinked from any parent, but belonging to this document.
        until child.null?
          following = child.get_pointer(LibXML::NEXT)
          nodes << Node.__wrap(child)
          child = following
        end
        nodes.each { |n| LibXML.xmlUnlinkNode(n.__topaz_ptr) }
        if status != 0 && (Integer(options) & LibXML::PARSE_RECOVER) == 0 && nodes.empty?
          error = LibXML.last_error
          document.errors << error if error && document.errors.respond_to?(:<<)
        end
        NodeSet.__from(document, nodes)
      end
    end

    class Element < Node; end
    class CharacterData < Node; end

    class Text < CharacterData
      def self.new(string, document, *rest, &block)
        text = LibXML.xmlNewDocText(Node.__document_ptr(document), LibXML.cstr(string.to_s))
        Node.__finish_new(Node.__wrap(text, self), [string, document, *rest], &block)
      end
    end

    class CDATA < Text
      def self.new(document, content, *rest, &block)
        content = content.to_s
        cdata = LibXML.xmlNewCDataBlock(Node.__document_ptr(document), LibXML.cstr(content), content.bytesize)
        Node.__finish_new(Node.__wrap(cdata, self), [document, content, *rest], &block)
      end
    end

    class Comment < CharacterData
      def self.new(document_or_node, content, *rest, &block)
        comment = LibXML.xmlNewDocComment(Node.__document_ptr(document_or_node), LibXML.cstr(content.to_s))
        Node.__finish_new(Node.__wrap(comment, self), [document_or_node, content, *rest], &block)
      end
    end

    class ProcessingInstruction < Node
      def self.new(document, name, content, *rest, &block)
        pi = LibXML.xmlNewDocPI(Node.__document_ptr(document), name.to_s, LibXML.cstr(content.to_s))
        Node.__finish_new(Node.__wrap(pi, self), [document, name, content, *rest], &block)
      end
    end

    class EntityReference < Node
      def self.new(document, name, *rest, &block)
        reference = LibXML.xmlNewReference(Node.__document_ptr(document), name.to_s)
        Node.__finish_new(Node.__wrap(reference, self), [document, name, *rest], &block)
      end
    end

    class Attr < Node
      def self.new(document, name, *rest, &block)
        attr = LibXML.xmlNewDocProp(Node.__document_ptr(document), name.to_s, FFI::Pointer::NULL)
        Node.__finish_new(Node.__wrap(attr, self), [document, name, *rest], &block)
      end

      def value=(value)
        encoded = LibXML.xmlEncodeEntitiesReentrant(document.__topaz_ptr, LibXML.cstr(value.to_s))
        LibXML.xmlNodeSetContent(@__topaz_ptr, encoded)
        LibXML::LibC.free(encoded) unless encoded.null?
        value
      end
    end

    class DTD < Node
      def external_id
        LibXML.string_at(@__topaz_ptr.get_pointer(LibXML::DTD_EXTERNAL_ID))
      end

      def system_id
        LibXML.string_at(@__topaz_ptr.get_pointer(LibXML::DTD_SYSTEM_ID))
      end

      def entities
        nil
      end

      def notations
        nil
      end

      def elements
        nil
      end

      def attributes
        nil
      end

      def validate(document)
        raise NotImplementedError, "DTD validation is not supported by topaz's Nokogiri"
      end
    end

    class AttributeDecl < Node; end
    class ElementDecl < Node; end
    class EntityDecl < Node; end

    class DocumentFragment < Node
      def self.native_new(document)
        fragment = LibXML.xmlNewDocFragment(Node.__document_ptr(document))
        Node.__wrap(fragment, self)
      end
    end

    class Document < Node
      def self.__wrap(pointer, klass = nil, args = [])
        address = pointer.address
        document = LibXML::DOCUMENTS[address]
        return document if document
        klass ||= pointer.get_int32(LibXML::TYPE) == LibXML::HTML_DOCUMENT_NODE ? HTML4::Document : Document
        document = klass.allocate
        document.instance_variable_set(:@__topaz_ptr, pointer)
        document.instance_variable_set(:@__topaz_nodes, {})
        document.instance_variable_set(:@decorators, nil)
        document.instance_variable_set(:@errors, nil)
        LibXML::DOCUMENTS[address] = document
        document.__send__(:initialize, *args)
        document
      end

      def self.new(version = "1.0", *rest, &block)
        document = __wrap(LibXML.xmlNewDoc(version.to_s), self, [version, *rest])
        yield document if block
        document
      end

      def self.read_memory(string, url, encoding, options)
        string = string.to_s
        LibXML.xmlResetLastError
        pointer = LibXML.xmlReadMemory(LibXML.cstr(string), string.bytesize, url&.to_s, encoding&.to_s, Integer(options))
        error = LibXML.last_error
        if pointer.null? || ((Integer(options) & LibXML::PARSE_RECOVER) == 0 && error)
          raise RuntimeError, "Could not parse document" if error.nil?
          raise XML::SyntaxError, "Parser without recover option encountered error or warning: #{error}"
        end
        document = __wrap(pointer, self)
        document.instance_variable_set(:@errors, error ? [error] : [])
        document
      end

      def self.read_io(io, url, encoding, options)
        read_memory(io.read.to_s, url, encoding, options)
      end

      def __topaz_nodes
        @__topaz_nodes
      end

      def document
        self
      end

      def root
        Node.__wrap(LibXML.xmlDocGetRootElement(@__topaz_ptr))
      end

      def root=(node)
        if node.nil?
          old = LibXML.xmlDocGetRootElement(@__topaz_ptr)
          LibXML.xmlUnlinkNode(old) unless old.null?
          return nil
        end
        pointer = node.__topaz_ptr
        if pointer.get_pointer(LibXML::DOC).address != @__topaz_ptr.address
          copy = LibXML.xmlDocCopyNode(pointer, @__topaz_ptr, 1)
          node.instance_variable_set(:@__topaz_ptr, copy)
          @__topaz_nodes[copy.address] = node
          pointer = copy
        end
        LibXML.xmlDocSetRootElement(@__topaz_ptr, pointer)
        node
      end

      def encoding
        LibXML.string_at(@__topaz_ptr.get_pointer(LibXML::DOC_ENCODING))
      end

      def encoding=(encoding)
        @__topaz_ptr.put_pointer(LibXML::DOC_ENCODING, LibXML.xmlStrdup(LibXML.cstr(encoding.to_s)))
        encoding
      end

      def version
        LibXML.string_at(@__topaz_ptr.get_pointer(LibXML::DOC_VERSION))
      end

      def url
        LibXML.string_at(@__topaz_ptr.get_pointer(LibXML::DOC_URL))
      end

      def remove_namespaces!
        remove = lambda do |pointer|
          until pointer.null?
            pointer.put_pointer(LibXML::NS, FFI::Pointer::NULL) if pointer.get_int32(LibXML::TYPE) == LibXML::ELEMENT_NODE
            pointer.put_pointer(LibXML::NS_DEF, FFI::Pointer::NULL) if pointer.get_int32(LibXML::TYPE) == LibXML::ELEMENT_NODE
            if pointer.get_int32(LibXML::TYPE) == LibXML::ELEMENT_NODE
              property = pointer.get_pointer(LibXML::PROPERTIES)
              until property.null?
                property.put_pointer(LibXML::NS, FFI::Pointer::NULL)
                property = property.get_pointer(LibXML::NEXT)
              end
            end
            remove.call(pointer.get_pointer(LibXML::CHILDREN))
            pointer = pointer.get_pointer(LibXML::NEXT)
          end
        end
        remove.call(@__topaz_ptr.get_pointer(LibXML::CHILDREN))
        self
      end

      def create_entity(name, type = 1, external_id = nil, system_id = nil, content = nil)
        entity = LibXML.xmlAddDocEntity(@__topaz_ptr, name.to_s, Integer(type), external_id&.to_s,
                                         system_id&.to_s, content&.to_s)
        raise RuntimeError, "Could not create entity" if entity.null?
        Node.__wrap(entity)
      end

      def canonicalize(*)
        raise NotImplementedError, "canonicalize is not supported by topaz's Nokogiri"
      end

      protected

      def protected_initialize_copy_with_args(other, level)
        copy = LibXML.xmlCopyDoc(other.__topaz_ptr, level)
        raise RuntimeError, "could not copy document" if copy.null?
        @__topaz_ptr = copy
        @__topaz_nodes = {}
        LibXML::DOCUMENTS[copy.address] = self
        self
      end
    end

    # A node set keeps its nodes in a Ruby array.
    class NodeSet
      def self.__from(document, nodes)
        set = allocate
        set.instance_variable_set(:@document, document)
        set.instance_variable_set(:@__topaz_nodes, nodes)
        document&.decorate(set)
        set
      end

      def __topaz_nodes
        @__topaz_nodes ||= []
      end

      def length
        __topaz_nodes.length
      end

      def push(node)
        raise ArgumentError, "node must be a Nokogiri::XML::Node or Nokogiri::XML::Namespace" unless node.is_a?(Node) || node.is_a?(Namespace)
        __topaz_nodes << node unless __topaz_nodes.any? { |n| n.equal?(node) }
        self
      end
      alias << push

      def [](*args)
        result = __topaz_nodes[*args]
        if result.is_a?(::Array)
          NodeSet.__from(@document, result)
        else
          result
        end
      end
      alias slice []

      def to_a
        __topaz_nodes.dup
      end
      alias to_ary to_a

      def delete(node)
        index = __topaz_nodes.index { |n| n.equal?(node) }
        index ? __topaz_nodes.delete_at(index) : nil
      end

      def include?(node)
        __topaz_nodes.any? { |n| n.equal?(node) }
      end

      def unlink
        __topaz_nodes.each(&:unlink)
        self
      end

      def |(other)
        raise ArgumentError, "node_set must be a Nokogiri::XML::NodeSet" unless other.is_a?(NodeSet)
        nodes = __topaz_nodes.dup
        other.__topaz_nodes.each { |n| nodes << n unless nodes.any? { |m| m.equal?(n) } }
        NodeSet.__from(@document, nodes)
      end

      def &(other)
        raise ArgumentError, "node_set must be a Nokogiri::XML::NodeSet" unless other.is_a?(NodeSet)
        NodeSet.__from(@document, __topaz_nodes.select { |n| other.include?(n) })
      end

      def -(other)
        raise ArgumentError, "node_set must be a Nokogiri::XML::NodeSet" unless other.is_a?(NodeSet)
        NodeSet.__from(@document, __topaz_nodes.reject { |n| other.include?(n) })
      end

      private

      def initialize_copy(other)
        super
        @__topaz_nodes = other.__topaz_nodes.dup
      end
    end

    class XPathContext
      def self.new(node)
        context = allocate
        pointer = LibXML.xmlXPathNewContext(node.document.__topaz_ptr)
        pointer.put_pointer(LibXML::XPATH_CONTEXT_NODE, node.__topaz_ptr)
        context.instance_variable_set(:@__topaz_ptr, pointer)
        context.instance_variable_set(:@__topaz_document, node.document)
        LibXML.xmlXPathRegisterNs(pointer, "nokogiri", "http://www.nokogiri.org/default_ns/ruby/extensions_functions")
        context
      end

      def node=(node)
        @__topaz_ptr.put_pointer(LibXML::XPATH_CONTEXT_NODE, node.__topaz_ptr)
        node
      end

      def register_ns(prefix, uri)
        LibXML.xmlXPathRegisterNs(@__topaz_ptr, prefix.to_s, uri.to_s)
        self
      end

      def register_variable(name, value)
        object = LibXML.xmlXPathNewString(LibXML.cstr(value.to_s))
        LibXML.xmlXPathRegisterVariable(@__topaz_ptr, name.to_s, object)
        self
      end

      # Nokogiri's CSS translation calls two builtin functions that its C
      # extension registers; without callbacks they are written out in
      # XPath.
      CSS_CLASS = /nokogiri-builtin:css-class\(\s*([^,()]+?)\s*,\s*(['"])(.*?)\2\s*\)/
      LOCAL_NAME_IS = /nokogiri-builtin:local-name-is\(\s*(['"])(.*?)\1\s*\)/

      def evaluate(expression, handler = nil)
        expression = expression.to_s
        if expression.include?("nokogiri-builtin:")
          expression = expression.gsub(CSS_CLASS) do
            "contains(concat(' ',normalize-space(#{$1}),' '),#{$2} #{$3} #{$2})"
          end
          expression = expression.gsub(LOCAL_NAME_IS) { "local-name()=#{$1}#{$2}#{$1}" }
        end
        LibXML.xmlResetLastError
        object = LibXML.xmlXPathEvalExpression(LibXML.cstr(expression), @__topaz_ptr)
        if object.null?
          error = LibXML.last_error(XPath::SyntaxError)
          raise(error || XPath::SyntaxError.new("Invalid expression: #{expression}"))
        end
        document = @__topaz_document
        result = case object.get_int32(LibXML::XPATH_TYPE)
                 when 1 # XPATH_NODESET
                   set = object.get_pointer(LibXML::XPATH_NODESET)
                   nodes = []
                   unless set.null?
                     count = set.get_int32(0)
                     table = set.get_pointer(8)
                     count.times do |i|
                       pointer = table.get_pointer(i * 8)
                       if pointer.get_int32(LibXML::TYPE) == LibXML::NAMESPACE_DECL
                         nodes << Namespace.__wrap(pointer, document)
                       else
                         nodes << Node.__wrap(pointer)
                       end
                     end
                   end
                   NodeSet.__from(document, nodes)
                 when 2 then object.get_int32(LibXML::XPATH_BOOLVAL) == 1
                 when 3 then object.get_double(LibXML::XPATH_FLOATVAL)
                 when 4 then LibXML.string_at(object.get_pointer(LibXML::XPATH_STRINGVAL))
                 else NodeSet.__from(document, [])
                 end
        LibXML.xmlXPathFreeObject(object)
        result
      end
    end

  end

  # Native methods of classes topaz does not support: they exist, so that
  # Nokogiri's Ruby files can alias and wrap them, and raise if called.
  {
    "XML::Reader" => %w[attribute attribute_at attribute_count attribute_hash attributes? base_uri
                        default? depth empty_element? encoding inner_xml lang local_name name
                        namespace_uri namespaces node_type outer_xml prefix read state value value?
                        xml_version],
    "XML::SAX::ParserContext" => %w[parse_with replace_entities= replace_entities recovery= recovery
                                    line column],
    "XML::SAX::PushParser" => %w[options options= replace_entities replace_entities= native_write],
    "XML::Schema" => %w[validate_document validate_file],
    "XSLT::Stylesheet" => %w[serialize transform],
    "XML::ElementContent" => %w[name type occur prefix c1 c2],
    "XML::AttributeDecl" => %w[attribute_type default enumeration],
    "XML::ElementDecl" => %w[element_type content prefix],
    "XML::EntityDecl" => %w[original_content content entity_type external_id system_id],
  }.each do |class_path, names|
    klass = class_path.split("::").inject(Nokogiri) { |mod, name| mod.const_get(name) }
    names.each do |name|
      next if klass.method_defined?(name, false) || klass.private_method_defined?(name, false)
      klass.define_method(name) do |*|
        raise NotImplementedError, "#{class_path}##{name} is not supported by topaz's Nokogiri"
      end
    end
  end

  class EncodingHandler
    def self.[](name)
      handler = LibXML.xmlFindCharEncodingHandler(name.to_s)
      return nil if handler.null?
      encoding = allocate
      encoding.instance_variable_set(:@name, LibXML.string_at(handler.get_pointer(0)) || name.to_s)
      encoding
    end

    def self.delete(name)
      LibXML.xmlDelEncodingAlias(name.to_s) == 0 ? true : nil
    end

    def self.alias(real_name, alias_name)
      LibXML.xmlAddEncodingAlias(real_name.to_s, alias_name.to_s)
      alias_name
    end

    def self.clear_aliases!
      LibXML.xmlCleanupEncodingAliases
      self
    end

    attr_reader :name
  end

  module HTML4
    class Document < XML::Document
      def self.new(uri = nil, external_id = nil, *rest, &block)
        document = __wrap(LibXML.htmlNewDoc(uri&.to_s, external_id&.to_s), self, [uri, external_id, *rest])
        yield document if block
        document
      end

      def self.read_memory(string, url, encoding, options)
        string = string.to_s
        LibXML.xmlResetLastError
        pointer = LibXML.htmlReadMemory(LibXML.cstr(string), string.bytesize, url&.to_s, encoding&.to_s, Integer(options))
        error = LibXML.last_error
        if pointer.null? || ((Integer(options) & LibXML::PARSE_RECOVER) == 0 && error)
          raise RuntimeError, "Could not parse document" if error.nil?
          raise XML::SyntaxError, "Parser without recover option encountered error or warning: #{error}"
        end
        document = __wrap(pointer, self)
        document.instance_variable_set(:@errors, error ? [error] : [])
        document
      end

      def self.read_io(io, url, encoding, options)
        read_memory(io.read.to_s, url, encoding, options)
      end

      def type
        LibXML::HTML_DOCUMENT_NODE
      end
    end

    # htmlElemDesc
    class ElementDescription
      def self.[](tag_name)
        pointer = LibXML.htmlTagLookup(tag_name.to_s)
        return nil if pointer.null?
        description = allocate
        description.instance_variable_set(:@__topaz_ptr, pointer)
        description
      end

      def name
        LibXML.string_at(@__topaz_ptr.get_pointer(0))
      end

      def implied_start_tag?
        @__topaz_ptr.get_uint8(8) != 0
      end

      def implied_end_tag?
        @__topaz_ptr.get_uint8(9) != 0
      end

      def save_end_tag?
        @__topaz_ptr.get_uint8(10) != 0
      end

      def empty?
        @__topaz_ptr.get_uint8(11) != 0
      end

      def deprecated?
        @__topaz_ptr.get_uint8(12) != 0
      end

      def inline?
        @__topaz_ptr.get_uint8(14) != 0
      end

      def description
        LibXML.string_at(@__topaz_ptr.get_pointer(16))
      end

      def sub_elements
        __strings(24)
      end

      def default_sub_element
        LibXML.string_at(@__topaz_ptr.get_pointer(32))
      end

      def optional_attributes
        __strings(40)
      end

      def deprecated_attributes
        __strings(48)
      end

      def required_attributes
        __strings(56)
      end

      private

      def __strings(offset)
        list = @__topaz_ptr.get_pointer(offset)
        return [] if list.null?
        strings = []
        i = 0
        until (item = list.get_pointer(i * 8)).null?
          strings << LibXML.string_at(item)
          i += 1
        end
        strings
      end
    end

    class EntityLookup
      def get(name)
        entity = LibXML.htmlEntityLookup(name.to_s)
        return nil if entity.null?
        EntityDescription.new(entity.get_uint32(0), LibXML.string_at(entity.get_pointer(8)),
                              LibXML.string_at(entity.get_pointer(16)))
      end
    end

    module SAX
      class Parser < XML::SAX::Parser; end
      class ParserContext < XML::SAX::ParserContext; end
      class PushParser < XML::SAX::PushParser; end
    end
  end

  module HTML5
    class Document < HTML4::Document; end
  end
end
