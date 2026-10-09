String-key Hash strategy validation
===================================

Measured on 2026-10-09. The baseline is Topaz revision ``2f3ce816``;
the comparison build adds StringDictStrategy. Both were translated with
``-Ojit`` using the same RPython checkout, revision
``1455033dc863ccb62858bf58ad5437e403a51863``. The new executable is
``bin/topaz``. Local builds, scripts, logs, and raw results are retained in
``.cache/string-hash-validation/`` (ignored by git).

Semantics and JIT checks
-----------------------

The strategy admits the same exact builtin strings as ObjectSpace's existing
fast paths. Subclasses, singleton-class strings, and other keys use object
storage. Ruby insertion still performs its existing copying/freezing before
strategy insertion; the dictionary retains those wrapped Ruby key objects.
Equality compares immutable strings and mutable character lists directly,
without allocating joined strings. Mutable probes are read afresh.

Validation results:

* Full untranslated suite: 1653 passed, 17 skipped, 7 expected failures.
* Final focused Hash suite, including an additional mixed-insertion order
  check: 50 passed. Hash and String suites together previously passed
  142 tests with one expected failure.
* Full translated JIT suite: 58 passed. The four new string tests fail on
  the baseline and pass on the new binary. They cover every combination of
  immutable/mutable stored keys and probes, changing lookup keys, updated
  values, and probe mutation after compilation.
* The steady immutable-key benchmark loop changes from
  ``call_may_force_i ... EF=7`` to ``call_i ... EF=5``. Its operation count
  falls from 63 to 42, excluding debug/portal markers, labels, and jumps.
  The new loop has no allocation or ``guard_not_forced``.

The callbacks do not call ObjectSpace.hash_w/eq_w or perform Ruby dispatch.
Tests replace both generic callbacks with failing functions. Inspection of
the generated JIT code and C call graph also confirms that string_eq reaches
only startswith__str_str and the three str/list compare_affix helpers.
string_hash reads the string strategy's existing storage hash directly.

Run the regression with::

    PYTHONPATH=/path/to/pypy pypy /path/to/pypy/pytest.py \
        -q tests/jit/test_hash.py --topaz=bin/topaz

Lookup benchmark
----------------

``hash_string_lookup.rb`` performs two million alternating successful
lookups per sample. Each process takes seven samples; the first is discarded.
Five paired processes per mode were run, alternating baseline/new order,
without trace logging and after the builds and tests had finished.

======================  =============  ========  =====================
Storage / control       Baseline (ms)  New (ms)  Paired median speedup
======================  =============  ========  =====================
Immutable strings       26.656         25.801    1.006x
Mutable strings         62.956         46.795    1.372x
Mixed-key object table  26.473         25.833    1.011x
======================  =============  ========  =====================

Times are medians of process medians. Speedups are medians of the five
paired ratios, so they need not equal the quotient of the time columns.
Immutable and mixed results are effectively unchanged within the observed
variation; mutable storage shows a clear improvement. These are lookup
microbenchmarks, not an application speedup estimate.

Run a mode with::

    bin/topaz bench/hash_string_lookup.rb constant
    bin/topaz bench/hash_string_lookup.rb mutable
    bin/topaz bench/hash_string_lookup.rb mixed

Raw samples and the paired runner are ``topaz-string-timings.json`` and
``topaz-string-measure.py`` in the local validation directory. The before/after
loop summaries are in ``topaz-string-micro-summary.txt``.

Lobsters trace comparison
-------------------------

Both builds ran the existing ruby-bench Lobsters workload with 15 warmup
and 25 measured iterations, CRuby 3.4.10 on PATH for Bundler, and
``PYPYLOG=jit-log-opt,jit-backend-counts,jit-summary``. Both successful runs
completed all 40 iterations. The supplied 11,476 count is not reused as
the baseline: the fresh baseline inventory contains 13,650 occurrences.

==================================  ========  =======
Metric                              Baseline  New
==================================  ========  =======
Forcing generic lookup occurrences  13,650    5,732
Non-forcing string occurrences      0         7,248
Estimated generic lookup calls      26.079M   13.436M
Estimated specialized string calls  0         12.452M
==================================  ========  =======

The forcing occurrence count falls by 58.0%. These are occurrences in
optimized traces, not execution counts. Traces change shape, so there is
no one-to-one correspondence between removed generic occurrences and new
string occurrences.

The separate call estimates weight operations by JIT backend entry/target
counters and subtract recorded compiled guard exits. They suggest about
48.5% less generic lookup traffic within compiled code for this run. They
exclude interpreted lookups and do not precisely account for exits without
compiled bridges. Neither statistic is an application-level speedup.
Logged wall-clock timings were not used to claim such a speedup.

Hot-site key types were checked both in trace storage reads and in a
separate, untimed runtime probe. Rack's environment had 44 exact String
keys; ActiveModel's type table had 24 exact String keys, and populated
attribute/casted-value caches also had exact String keys. The new traces
show non-forcing string lookups in ActiveModel::LazyAttributeSet#fetch_value,
ActiveModel::AttributeSet#[], ActiveRecord::Result's column-name indexes,
and Rack::Request#get_header.

An important remaining case is ActiveRecord::Result#column_types: the
runtime probe found 24 integer and 24 exact String keys. Its filtered
additional_types table retained integer keys while receiving String
lookups. These need generic storage. Also, an incompatible lookup can
convert a table to object storage even if its stored keys are all strings;
the implementation conservatively preserves custom-key equality.

The largest remaining generic sites were checked separately as well:
ActiveSupport's isolated execution state mixed Symbol and exact String
keys, while concurrent-ruby map caches mixed nil and exact String keys
(other cache instances had Hash keys). A String probe alone therefore
does not establish that its table can use the string strategy.

The comparison logs, counter analyses, and key-probe output are
``topaz-string-lobsters-{before,after}.log.gz``,
``topaz-string-{before,after}-analysis.json``, and
``topaz-string-key-probe*.out`` in the local validation directory.
The first new-build capture hit the temporary-directory quota while saving
results and is retained with ``after-failed`` in its name; it is excluded
from the comparison. All task artifacts were moved into the checkout.

For another run, use the same settings with the appropriate binary and
output paths::

    WARMUP_ITRS=15 MIN_BENCH_ITRS=25 MIN_BENCH_TIME=0 \
    RESULT_JSON_PATH=/path/to/results.json \
    PYPYLOG=jit-log-opt,jit-backend-counts,jit-summary:/path/to/jit.log \
        /path/to/topaz -I harness benchmarks/lobsters/benchmark.rb

Run from the ruby-bench checkout. The local ``analyze-string-hash.py``
records static counts and counter-weighted estimates. Its specialized
trampoline name was identified from the microbenchmark trace and must be
checked again when analyzing a different build.
