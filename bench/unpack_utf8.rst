UTF-8 unpack specialization
==========================

Implementation
--------------

``unpack('U')`` and the offset-zero ``unpack1('U')`` / ``unpack1('U*')``
fast paths now decode one codepoint without entering a decoding JIT portal.
The decoder specializes on the underlying string or character-list storage.
Its small continuation-byte loop can be unrolled, and the caller can eliminate
the temporary result array and boxed integer when their uses permit it.

The decoder raises a lightweight internal exception. Ruby ArgumentError
construction happens in the Ruby method wrapper, outside the bulk portal.
Existing error messages and precedence are preserved, including checking
truncation before continuation bytes. Existing acceptance of surrogates and
four-byte values above U+10FFFF is also preserved.

For bulk decoding, two translated alternatives were measured: an ordinary
storage-specialized RPython loop behind ``jit.dont_look_inside``, and a retained
driver with the storage strategy as a green. The latter is selected: although
the ordinary loop wins for tiny inputs, the strategy-green driver performs
better on longer inputs. There is no input-size heuristic.

Validation environment
----------------------

Measurements were taken on 2026-10-09 against baseline ``34be4fa2`` using
RPython checkout ``1455033dc863ccb62858bf58ad5437e403a51863``. Baseline, ordinary
loop, and strategy-green variants were freshly translated with JIT enabled
and two compilation jobs. ``bin/topaz`` contains the selected rebuilt binary.

The selected implementation passed 1,723 unit tests (17 skipped, 7 expected
failures) and all 90 JIT tests. Focused coverage includes empty inputs, ASCII,
two- through four-byte sequences, malformed inputs and exact error messages,
both storage strategies, mutation, trailing malformed bytes, block results,
private count arguments, and the offset fallback.

The single-codepoint structural JIT regression has 18 parameter combinations
covering both storages, three public expressions, and three character widths.
It checks for direct byte loads and absence of calls, allocations, and
``guard_not_forced``. All 18 failed against the old binary and pass against
the new binary. Additional JIT tests cover mixed widths, empty inputs,
in-place mutation, and exceptions after warmup, including bulk decoding.

Microbenchmarks
---------------

``bench/unpack_utf8.rb`` alternates two strings, checks the result, warms the
caller, and emits five timings. Each process discards its first timing; the
remaining four are summarized by their median. Three rounds rotate the order
of the three binaries. Tables show the median of the three process medians;
reported speedups use the median of paired round ratios. Builds, tests, and
Lobsters were idle during these measurements.

Single-codepoint timings, milliseconds per million calls:

================ ======= ======== ======== ========
Expression       Input   Storage  Baseline Selected
================ ======= ======== ======== ========
unpack('U')[0]   ASCII   constant 29.428   1.737
unpack('U')[0]   ASCII   mutable  29.188   1.825
unpack('U')[0]   2-byte  constant 27.986   2.521
unpack('U')[0]   2-byte  mutable  27.962   2.619
unpack1('U')     ASCII   constant 27.915   1.728
unpack1('U')     ASCII   mutable  27.772   1.843
unpack1('U')     2-byte  constant 29.372   2.466
unpack1('U')     2-byte  mutable  29.661   2.576
================ ======= ======== ======== ========

Paired speedups range from 10.86x to 16.16x. These loops consume the integer
directly; applications that retain arrays or boxed values may benefit less.

Long bulk timings, milliseconds per approximately ten million codepoints.
Mixed input repeats an ASCII, two-byte, three-byte, and four-byte sequence:

===== ======== =========== ======== ======== ========
Input Storage  Codepoints Baseline Ordinary Selected
===== ======== =========== ======== ======== ========
ASCII constant 64          34.996   45.890   34.740
ASCII constant 1024        43.451   54.331   39.663
ASCII mutable  64          34.977   47.991   33.871
ASCII mutable  1024        39.929   54.387   38.898
Mixed constant 256         43.242   49.487   39.059
Mixed constant 4096        65.425   79.918   60.776
Mixed mutable  256         44.047   53.081   40.591
Mixed mutable  4096        65.119   80.426   63.814
===== ======== =========== ======== ======== ========

The selected driver takes 21--30% less time than the ordinary loop here,
and is 1--12% faster than baseline. Conversely, constant-storage single-ASCII
``U*`` calls took 15.479 ms with the ordinary loop versus 24.850 ms with the
selected driver per million codepoints; four-codepoint mixed inputs took
7.118 versus 8.333 ms. Retaining the driver favors sustained bulk throughput.

Trace evidence
--------------

In the steady microbenchmark caller for ``unpack('U')[0]``, the baseline has
one ``call_assembler_r``, one ``guard_not_forced``, and three allocation
operations (list object, empty backing array, and virtual-reference object).
The selected version has none of these calls, guards, or allocations for
ASCII, two-byte, and four-byte inputs. Its result array and boxed integer are
virtual. Ordinary Ruby-frame ``force_token`` pseudo-operations remain.

Excluding debug markers, portal markers, label, and jump, the baseline caller
has 74 operations. The selected caller has 44, 59, and 79 operations for the
three widths respectively. The baseline count excludes decoding and
allocations inside the callee, whereas the selected caller includes decoding;
these operation totals must not be read as execution-cost ratios.

Lobsters ran for 40 iterations (15 warmup and 25 measured) with optimized
traces, backend counters, and the JIT summary enabled. Both runs completed.
The old log has five calls to the UTF-8 decoding portal: three with a literal
count of one and two bulk calls. The new log has only the two bulk calls,
targeting ``String#unpack(U*)``. The nine caller-side allocation operations
associated with the three single-codepoint portal sites disappear.

Two old single-codepoint sites are rooted in htmlentities' ``replace_basic``;
the third is a shared unpack bridge. A representative new htmlentities
``encode_decimal`` trace guards ConstantStringStrategy, reads the string
length and first byte directly, checks the ASCII range, and passes the
unboxed codepoint to integer formatting. No decoding portal or result-array
allocation intervenes. Other encoder work still allocates, and other
consumers may require boxing (for example to use the codepoint as a Hash key).

Backend-counter estimates attribute about 79,782 compiled calls to the old
single-codepoint portal sites, corresponding to 239,346 caller allocation
operations. These are estimates from trace entry/target counts with recorded
compiled guard exits subtracted, not a complete execution profile: interpreted
execution and exits without compiled counters are not fully represented.
The static three-to-zero site count alone says nothing about frequency.
No application wall-time speedup is claimed: these Lobsters runs overlapped
other validation work and serve as trace comparisons only.

Reproduction and local artifacts
-------------------------------

Example benchmark commands::

    bin/topaz bench/unpack_utf8.rb unpack utf8 constant
    bin/topaz bench/unpack_utf8.rb unpack1 ascii mutable
    bin/topaz bench/unpack_utf8.rb bulk utf8 mutable 1024 10000000

Test commands (with PyPy 2 and the RPython checkout on PYTHONPATH)::

    pypy ../gitpypy/pytest.py -q tests --ignore=tests/jit
    pypy ../gitpypy/pytest.py -q tests/jit --topaz=bin/topaz

All local temporary files live under the ignored checkout directory
``.cache/utf8-unpack-validation/``, including ``tmp/`` used as TMPDIR.
This directory retains the baseline, ordinary-loop (``plain``), and selected
(``green``) source snapshots and binaries; three build logs; test logs;
``measure.py`` and ``measure-long.py``; raw timing JSON and summaries;
``micro-traces.py`` and extracted micro traces; compressed
``lobsters-before.log.gz`` / ``lobsters-after.log.gz``; ``analyze.py`` and its
JSON summaries; and representative ``html-before-0.trace`` /
``html-after-0.trace`` extracts. These large local artifacts are not committed.
