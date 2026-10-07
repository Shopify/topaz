#!/bin/sh
# Builds libsqlite3.so from the SQLite source the sqlite3 gem bundles, with
# the gem's compile options, so topaz's FFI binding runs the same SQLite
# as CRuby's sqlite3 extension. (A distribution's libsqlite3 may enable
# options such as statement scan status that make queries markedly
# slower.) Then run with TOPAZ_LIBSQLITE3=<outdir>/libsqlite3.so.0.
#
#   tools/ruby-bench/build_sqlite.sh $BUNDLE_PATH/ruby/4.0.0/gems/sqlite3-2.7.3 outdir
set -e
gem=$1
out=${2:-.}
src=$(find "$gem" -name sqlite3.c -path '*sqlite-autoconf*' | head -1)
if [ -z "$src" ]; then
  tarball=$(ls "$gem"/ports/archives/sqlite-autoconf-*.tar.gz | head -1)
  tmp=$(mktemp -d)
  tar -xzf "$tarball" -C "$tmp"
  src=$(find "$tmp" -name sqlite3.c | head -1)
fi
mkdir -p "$out"
case "$(uname)" in
  Darwin) lib=libsqlite3.dylib; soname="" ;;
  *) lib=libsqlite3.so.0; soname="-Wl,-soname,libsqlite3.so.0" ;;
esac
# The gem's options (ext/sqlite3/extconf.rb), plus column metadata, which
# the binding's column_database_name needs.
cc -O2 -fPIC -shared -o "$out/$lib" $soname \
  -DSQLITE_DEFAULT_WAL_SYNCHRONOUS=1 -DSQLITE_USE_URI=1 \
  -DSQLITE_ENABLE_DBPAGE_VTAB=1 -DSQLITE_ENABLE_DBSTAT_VTAB=1 \
  -DSQLITE_ENABLE_FTS5 -DSQLITE_ENABLE_MATH_FUNCTIONS -DSQLITE_THREADSAFE=1 \
  -DSQLITE_ENABLE_COLUMN_METADATA \
  "$src" -lm -lpthread
echo "$out/$lib"
