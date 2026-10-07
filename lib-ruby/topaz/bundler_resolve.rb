# Run by CRuby under `bundle exec` from topaz's Bundler.setup, to print the
# resolved bundle: a "path" line per require path of each gem (excluding
# Bundler itself), a "stdlib" line per directory of CRuby's pure-Ruby
# standard library, and a "dep" line per Gemfile dependency with its
# groups and what Bundler.require would require for it.
require "rbconfig"

Bundler.definition.specs.each do |spec|
  next if spec.name == "bundler"
  spec.full_require_paths.each { |path| puts ["path", path].join("\t") }
end

RbConfig::CONFIG.values_at("sitelibdir", "vendorlibdir", "rubylibdir").each do |dir|
  puts ["stdlib", dir].join("\t") if dir && File.directory?(dir)
end

Bundler.definition.dependencies.each do |dep|
  next unless dep.should_include?
  explicit = !dep.autorequire.nil?
  files = dep.autorequire || [dep.name]
  puts ["dep", dep.name, dep.groups.join(","), explicit ? "explicit" : "default", files.join(",")].join("\t")
end
