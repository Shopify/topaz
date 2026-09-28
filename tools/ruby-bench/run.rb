# Run a ruby-bench benchmark on topaz with gems installed by CRuby:
#   topaz run.rb path/to/benchmark.rb
#
# The load path is: stand-ins for things topaz lacks (shim/), the gems'
# lib directories, topaz's own library, then CRuby's pure-Ruby stdlib.
here = File.expand_path(__dir__)
paths = File.read(File.join(here, "load_path.txt")).split("\n")
paths = paths.reject { |p| p.include?("x86_64-linux") || p.include?("/gems/bundler-") }
gems = paths.select { |p| p.include?("/gems/") }
stdlib = paths.reject { |p| p.include?("/gems/") }
$LOAD_PATH.replace([File.join(here, "shim")] + gems + $LOAD_PATH + stdlib)
bench = ARGV.shift
$0 = bench
load bench
