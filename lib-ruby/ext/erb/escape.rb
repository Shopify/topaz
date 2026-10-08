# Topaz's erb/escape.so: ERB::Escape.html_escape over the RPython loop
# String#__topaz_escape_html, as CRuby's C extension. The string itself
# comes back when it has nothing to escape; otherwise a new String in
# the same encoding.
module ERB::Escape
  def html_escape(s)
    s = s.to_s unless s.is_a?(String)
    enc = s.encoding
    return CGI.escapeHTML(s) unless enc.ascii_compatible?
    escaped = s.__topaz_escape_html
    unless escaped.equal?(s) || enc.equal?(Encoding::UTF_8)
      escaped.force_encoding(enc)
    end
    escaped
  end
  module_function :html_escape
end
