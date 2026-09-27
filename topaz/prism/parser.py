"""Parse Ruby source with Prism into Topaz's AST."""

from topaz.prism import binding, nodes
from topaz.prism.translate import Translator, TranslateError


class ParseError(Exception):
    def __init__(self, msg, lineno):
        self.msg = msg
        self.lineno = lineno


def parse(source, initial_lineno, symtable):
    """Parse `source` into an ast.Main, declaring its variables in
    `symtable`. Variables already declared in `symtable` (the locals of a
    Binding being eval'd in) are visible to the source."""
    scopes = []
    names = symtable.cells.keys()
    if names:
        scopes.append(binding.Scope(names))
    options = binding.serialize_options("", initial_lineno, scopes)
    loader = nodes.Loader(source, binding.serialize_parse(source, options))
    try:
        program = loader.load()
    except nodes.LoadError as e:
        raise ParseError(e.msg, initial_lineno)
    if loader.errors:
        error = loader.errors[0]
        raise ParseError(error.message, loader.line_of(error.location.start))
    try:
        return Translator(loader, symtable).translate(program)
    except TranslateError as e:
        raise ParseError(e.msg, e.lineno)
