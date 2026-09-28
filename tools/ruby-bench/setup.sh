#!/bin/sh
# Installs a ruby-bench benchmark's gems with CRuby and records, for run.rb,
# the load path CRuby's Bundler sets up and the files Bundler.require loads.
#
#   tools/ruby-bench/setup.sh path/to/ruby-bench/benchmarks/lobsters
#
# Needs CRuby (with bundler) on PATH, and BUNDLE_PATH set to where the gems
# should go.
set -e
here=$(cd "$(dirname "$0")" && pwd)
cd "$1"
bundle install
RAILS_ENV=${RAILS_ENV:-production} bundle exec ruby -e '
here = ARGV[0]
File.write(File.join(here, "load_path.txt"), $LOAD_PATH.join("\n") + "\n")
groups = [:default, (ENV["RAILS_ENV"] || "production").to_sym]
requires = []
Bundler.definition.dependencies.each do |dep|
  next unless (dep.groups & groups).any? && dep.should_include?
  requires.concat(dep.autorequire || [dep.name])
end
File.write(File.join(here, "bundler_requires.txt"), requires.join("\n") + "\n")
' "$here"
