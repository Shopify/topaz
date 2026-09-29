# Running ruby-bench benchmarks on topaz

Topaz has no RubyGems or Bundler. To run a
[ruby-bench](https://github.com/ruby/ruby-bench) benchmark that has a
Gemfile, let CRuby install the gems, then run topaz with CRuby's load path:

    export BUNDLE_PATH=$HOME/ruby-bench-gems
    tools/ruby-bench/setup.sh ~/ruby-bench/benchmarks/lobsters
    cd ~/ruby-bench
    bin/topaz -I harness-once ~/topaz/tools/ruby-bench/run.rb benchmarks/lobsters/benchmark.rb

`setup.sh` writes `load_path.txt` and `bundler_requires.txt` here. `run.rb`
puts `shim/` (a stand-in `bundler`), the gems' directories, topaz's own
library and then CRuby's pure-Ruby standard library on the load path, and
loads the benchmark. Add `-r tools/ruby-bench/trace_require.rb` and set
`TRACE_REQUIRE=1` to print each `require` as it happens.

Topaz cannot load C extensions. For the ones lobsters needs (sqlite3,
nokogiri, bcrypt, markly, and the C parts of CRuby's standard library such
as psych, date, strscan, json, digest, openssl, zlib and bigdecimal),
`lib-ruby/ext` has replacements in Ruby, most of them FFI bindings to the
same C libraries, which must be on `LD_LIBRARY_PATH`.

For timings comparable with CRuby, give the sqlite3 binding the SQLite the
gem itself builds, rather than a distribution's libsqlite3 (whose extra
compile options made lobsters' queries several times slower):

    tools/ruby-bench/build_sqlite.sh $BUNDLE_PATH/ruby/4.0.0/gems/sqlite3-2.7.3 ~/sqlite-gem
    export TOPAZ_LIBSQLITE3=~/sqlite-gem/libsqlite3.so.0
