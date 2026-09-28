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

Gems with C extensions (sqlite3, nokogiri, bcrypt, ...) and the parts of
CRuby's standard library written in C (psych, date, strscan, json, digest,
openssl, zlib, bigdecimal, ...) do not load on topaz.
