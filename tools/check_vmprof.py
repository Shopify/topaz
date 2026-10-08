#!/usr/bin/env python3
"""Check a translated Topaz with the standard vmprof reader.

Usage: python3 tools/check_vmprof.py bin/topaz [--native] [--jit]
Requires the Python vmprof package. No JIT is required.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import vmprof
from vmprof.reader import JittedCode


SOURCE = """
def burn
  i = 0
  while i < 100_000
    i += 1
  end
end

def hot_outer
  20.times { burn }
end

def nested_work
  20.times { burn }
end

def fiber_work
  Fiber.new { nested_work }.resume
  20.times do
    burn
    Fiber.yield
  end
end

def main_work
  burn
end

def raised_work
  burn
  raise "expected"
end

def rescued_work
  20.times { burn }
end

def exit_work
  20.times { burn }
end

at_exit { exit_work }
hot_outer
fiber = Fiber.new { fiber_work }
20.times do
  fiber.resume
  main_work
end
# Resume once more so the Fiber finishes, rather than remaining suspended.
fiber.resume
main_work
begin
  raised_work
rescue
  rescued_work
end
begin
  Fiber.new { raised_work }.resume
rescue
  rescued_work
end
%s
"""


def check(binary, directory, ending, status, native=False, jit=False):
    script = directory / ("case%d.rb" % status)
    profile = directory / ("case%d.prof" % status)
    source = SOURCE % ending
    if jit:
        # Keep each phase long enough to sample after its loops compile.
        source = source.replace("100_000", "100_000_000")
    script.write_text(source)
    env = dict(os.environ, TOPAZ_VMPROF=str(profile))
    result = subprocess.run([binary, str(script)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=120)
    assert result.returncode == status, result.stderr.decode()
    stats = vmprof.read_profile(str(profile))
    assert stats.end_time is not None, "missing profile trailer"
    assert stats.profiles, "no samples"

    stacks = []
    for sample in stats.profiles:
        names = []
        for addr in sample[0]:
            info = stats.get_addr_info(addr)
            if info is not None and info[0] == "rb":
                names.append(info[1])
        stacks.append(names)
    for caller in ("hot_outer", "fiber_work", "nested_work", "main_work",
                   "rescued_work", "exit_work"):
        assert any(caller in s and "burn" in s for s in stacks), caller
    for stack in stacks:
        if "main_work" in stack:
            assert "fiber_work" not in stack, "suspended Fiber leaked into main stack"
        if "rescued_work" in stack:
            assert "raised_work" not in stack, "exception left a stale frame"
    if jit:
        compiled = [sample for sample in stats.profiles
                    if any(isinstance(addr, JittedCode) and
                           stats.get_addr_info(addr) is not None and
                           stats.get_addr_info(addr)[1] == "burn"
                           for addr in sample[0])]
        assert compiled, "no samples inside JIT-compiled burn"
        print("  %d samples inside JIT-compiled burn" % len(compiled))
    # Exercise the same tree construction used by vmprofshow.
    assert stats.get_tree() is not None
    if native:
        native_names = [name for name, count in stats.top_profile()
                        if name.startswith("n:")]
        assert native_names, "no native frames sampled (check libunwind)"
        assert any(not name.startswith("n:<native symbol") for name in native_names), \
            "native addresses were not resolved"
        assert any(name.startswith("n:pypy_g_") for name in native_names), \
            "local RPython function symbols were not resolved"
        assert any(any(stats.get_addr_info(a)[0] == "n" for a in sample[0]
                       if stats.get_addr_info(a) is not None) and
                   any(stats.get_addr_info(a)[0] == "rb" for a in sample[0]
                       if stats.get_addr_info(a) is not None)
                   for sample in stats.profiles), "no mixed Ruby/native stacks"
        resolved = sum(not name.startswith("n:<native symbol") for name in native_names)
        print("  %d/%d native functions resolved" % (resolved, len(native_names)))
    print("exit %d: %d samples; Ruby callers, Fibers, exceptions and at_exit OK" %
          (status, len(stats.profiles)))


def main():
    binary = os.path.abspath(sys.argv[1])
    with tempfile.TemporaryDirectory(prefix="topaz-vmprof-check-") as path:
        directory = Path(path)
        for ending, status in (("", 0), ("exit 7", 7), ('raise "unhandled"', 1)):
            check(binary, directory, ending, status,
                  "--native" in sys.argv[2:], "--jit" in sys.argv[2:])


if __name__ == "__main__":
    main()
