#!/bin/sh
# Runs each script here with a topaz binary and compares what it prints with
# what CRuby 4.0 printed (the .expected files, from ruby 4.0.6).
#
#   tests/compat/run.sh [path/to/topaz]
cd "$(dirname "$0")"
topaz=${1:-../../bin/topaz}
pass=0
fail=0
for f in *.rb; do
  name=${f%.rb}
  if "$topaz" "$f" > "/tmp/topaz-compat-$name.out" 2>&1 &&
      cmp -s "/tmp/topaz-compat-$name.out" "$name.expected"; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    echo "DIFF: $name (see /tmp/topaz-compat-$name.out)"
  fi
done
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
