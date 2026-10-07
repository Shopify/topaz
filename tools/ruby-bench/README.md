# Running ruby-bench benchmarks on topaz

Topaz has no RubyGems or Bundler of its own, but its standard library has
stand-ins (`lib-ruby/rubygems.rb`, `lib-ruby/bundler.rb`) that use
CRuby's: a benchmark's `bundle install` runs CRuby's `bundle` from PATH,
and topaz's `Bundler.setup` asks `bundle exec ruby` for the resolved
Gemfile, then puts the gems' directories before, and CRuby's pure-Ruby
standard library after, topaz's own library on the load path.
`Bundler.require` replays the requires CRuby's would do. So a
[ruby-bench](https://github.com/ruby/ruby-bench) benchmark runs as it
does on CRuby, with CRuby (and its bundler) on PATH:

    cd ~/ruby-bench
    ~/topaz/bin/topaz -I harness-once benchmarks/lobsters/benchmark.rb

Add `-r ~/topaz/tools/ruby-bench/trace_require.rb` and set
`TRACE_REQUIRE=1` to print each `require` as it happens.

Topaz cannot load C extensions. For the ones lobsters needs (sqlite3,
nokogiri, bcrypt, markly, and the C parts of CRuby's standard library such
as psych, date, strscan, json, digest, openssl, zlib and bigdecimal),
`lib-ruby/ext` has replacements in Ruby, most of them FFI bindings to the
same C libraries. `Topaz::NativeLibrary` (`lib-ruby/topaz/native_library.rb`)
finds those libraries: through their `TOPAZ_LIB*` variables, in Homebrew's
directories on macOS, by name through the dynamic linker, and, for the
ones no system ships (bcrypt's crypt_blowfish, markly's cmark-gfm), by
building them from the gem's own sources with `cc` into `~/.cache/topaz`.

For timings comparable with CRuby, give the sqlite3 binding the SQLite the
gem itself builds, rather than a distribution's libsqlite3 (whose extra
compile options made lobsters' queries several times slower):

    tools/ruby-bench/build_sqlite.sh $(bundle info sqlite3 --path) ~/sqlite-gem
    export TOPAZ_LIBSQLITE3=~/sqlite-gem/libsqlite3.so.0   # .dylib on macOS
