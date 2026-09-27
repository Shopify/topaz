import sys
import os
import platform
import subprocess

IS_POSIX = os.name == "posix"
IS_WINDOWS = os.name == "nt"
IS_LINUX = "linux" in sys.platform
IS_64BIT = "64bit" in platform.architecture()[0]
IS_CYGWIN = "cygwin" == sys.platform

try:
    RUBY_REVISION = subprocess.check_output([
        "git",
        "--git-dir", os.path.join(os.path.dirname(
            os.path.abspath(__file__)), os.pardir, ".git"),
        "rev-parse", "--short", "HEAD"
    ]).rstrip()
except subprocess.CalledProcessError:
    RUBY_REVISION = "unknown"

if IS_WINDOWS:
    os_name = "Windows"
    cpu = "x86_64" if IS_64BIT else "i686"
else:
    os_name, _, _, _, cpu = os.uname()

RUBY_PLATFORM = "%s-%s" % (cpu, os_name.lower())
RUBY_ENGINE = "topaz"
# The language version Topaz targets.
RUBY_VERSION = "4.0.0"
RUBY_PATCHLEVEL = 0
RUBY_RELEASE_DATE = "2025-12-25"
RUBY_COPYRIGHT = "ruby - Copyright (C) 1993-2025 Yukihiro Matsumoto"
# Topaz has never had releases of its own, so it reports the language
# version it implements, like CRuby does.
RUBY_ENGINE_VERSION = RUBY_VERSION
RUBY_DESCRIPTION = "%s (ruby-%sp%d) (git rev %s) [%s]" % (
    RUBY_ENGINE, RUBY_VERSION, RUBY_PATCHLEVEL, RUBY_REVISION, RUBY_PLATFORM)
