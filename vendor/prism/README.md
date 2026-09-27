Prism
=====

This directory is a vendored copy of the C sources of
[Prism](https://github.com/ruby/prism), the Ruby parser that CRuby itself
uses since Ruby 3.4.  Topaz parses Ruby with it: Prism serializes its syntax
tree (see `serialization.md`), `topaz/prism/nodes.py` (generated from
`config.yml` by `topaz/prism/gen.py`) loads it, and `topaz/prism/translate.py`
turns it into Topaz's own AST.

Version: 1.8.1, the Prism release shipped with Ruby 4.0.

The files come from the `prism-1.8.1` gem, which unlike the git repository
contains the generated sources (`include/prism/ast.h`, `src/node.c`,
`src/serialize.c`, ...).  `include/`, `src/`, `config.yml` and `LICENSE.md` are
copied verbatim.

To upgrade:

    gem fetch prism -v X.Y.Z && gem unpack prism-X.Y.Z.gem
    rm -rf vendor/prism/include vendor/prism/src
    cp -r prism-X.Y.Z/{include,src,config.yml,LICENSE.md,docs/serialization.md} vendor/prism/
    python3 topaz/prism/gen.py          # needs a `ruby` to read config.yml

then update the version above and check `topaz/prism/binding.py` still
matches the options format described in `serialization.md`.
