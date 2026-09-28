# On MRI, this file gets created by mkconfig.rb when ruby is
# built. Our config is adapted from Rubinius.

unless RUBY_ENGINE == "topaz"
  raise "Looks like you loaded the Topaz rbconfig, but this is not Topaz."
end

module RbConfig
  prefix = File.dirname(File.dirname(__FILE__))
  major, minor, teeny = RUBY_VERSION.split(".")
  cpu, os = RUBY_PLATFORM.split("-", 2)

  CONFIG = {}

  CONFIG["prefix"]               = prefix
  CONFIG["exec_prefix"]          = prefix
  CONFIG["bindir"]               = File.join(prefix, "bin")
  CONFIG["libdir"]               = File.join(prefix, "lib")
  CONFIG["rubylibprefix"]        = prefix
  CONFIG["rubylibdir"]           = File.join(prefix, "lib-ruby")
  CONFIG["rubyarchdir"]          = File.join(prefix, "lib-ruby")
  CONFIG["sitedir"]              = File.join(prefix, "lib-ruby", "site_ruby")
  CONFIG["sitelibdir"]           = File.join(prefix, "lib-ruby", "site_ruby")
  CONFIG["sitearchdir"]          = File.join(prefix, "lib-ruby", "site_ruby")
  CONFIG["vendordir"]            = File.join(prefix, "lib-ruby", "vendor_ruby")
  CONFIG["vendorlibdir"]         = File.join(prefix, "lib-ruby", "vendor_ruby")
  CONFIG["datadir"]              = File.join(prefix, "share")
  CONFIG["ruby_install_name"]    = RUBY_ENGINE.dup
  CONFIG["RUBY_INSTALL_NAME"]    = RUBY_ENGINE.dup
  CONFIG["RUBY_BASE_NAME"]       = RUBY_ENGINE.dup
  CONFIG["RUBY_PROGRAM_VERSION"] = RUBY_VERSION.dup
  CONFIG["ruby_version"]         = RUBY_VERSION.dup
  CONFIG["MAJOR"]                = major
  CONFIG["MINOR"]                = minor
  CONFIG["TEENY"]                = teeny
  CONFIG["PATCHLEVEL"]           = RUBY_PATCHLEVEL.to_s
  CONFIG["arch"]                 = RUBY_PLATFORM.dup
  CONFIG["host_cpu"]             = cpu
  CONFIG["target_cpu"]           = cpu
  CONFIG["host_os"]              = os
  CONFIG["target_os"]            = os
  CONFIG["build_os"]             = os
  CONFIG["exeext"]               = ""
  CONFIG["EXEEXT"]               = ""
  CONFIG["DLEXT"]                = "so"
  CONFIG["SOEXT"]                = "so"
  CONFIG["LIBEXT"]               = "a"
  CONFIG["OBJEXT"]               = "o"
  CONFIG["PATH_SEPARATOR"]       = ":"

  def self.ruby
    File.join(CONFIG["bindir"], CONFIG["ruby_install_name"] + CONFIG["EXEEXT"])
  end
end

