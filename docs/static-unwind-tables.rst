Static unwind tables for Topaz
=============================

Status: implemented, 2026-10-10. The design below records the migration
constraints; implementation details and validation follow at the end.

Replace per-execution ``FrameBlock`` objects with immutable metadata owned by
``W_CodeObject``. Recover the active handler chain from the bytecode PC when
control flow needs it. Keep Topaz's existing rescue/ensure bodies in the same
code object and retain its nonlocal return, break, and throw machinery during
the initial migration.

The objective is to remove handler allocation and handler-chain updates on
ordinary execution, including when a frame escapes to another compiled loop.
This is the same principle as CRuby's catch tables and CPython's exception
tables. It does not make raising exceptions or executing ensure bodies free.

Motivation and previous implementation
--------------------------------------

``SETUP_LOOP``, ``SETUP_EXCEPT``, and ``SETUP_FINALLY`` in
``topaz/interpreter.py`` allocate a linked ``FrameBlock`` and assign it to
``Frame.lastblock``. Each block records a target PC, a stack depth, and its
parent. ``POP_BLOCK`` removes it and performs stack cleanup. Unwinding walks
the chain until it finds a block accepting the control-flow reason.

The JIT can virtualize these objects, but not in every context. Inspection of
``_build/array-drivers/lobsters-full-100-after/jit.log.gz`` found 513 explicit
FrameBlock allocation sites in optimized traces. One steady-state unpack
trace materializes an ``Integer#times`` loop block, stores it in a materialized
frame, and passes that frame to ``call_assembler``. These are trace-site
counts, not execution counts, and that capture used the experimental Array
drivers; a current baseline is required before measuring this proposal.

Relevant source components:

* ``topaz/ast.py``: ``BaseLoop``, ``TryExcept``, ``TryFinally``, ``Next``,
  ``Break``, ``Return``, ``Redo``, and ``Retry``.
* ``topaz/astcompiler.py``: compiler block tracking, CFG layout, stack-depth
  calculation, and jump relocation.
* ``topaz/interpreter.py``: bytecode dispatch, exception handlers,
  ``SuspendedUnroller`` subclasses, and ``FrameBlock`` subclasses.
* ``topaz/frame.py``: ``lastblock``, stack cleanup, and unwinding.
* ``topaz/objects/codeobject.py``: immutable code metadata and deep copying.

What CRuby's compiler does
-------------------------

The inspected checkout is ``/home/cfbolz/projects/misc/ruby``. Both compiler
frontends use the same final assembly machinery:

* ``prism_compile.c:pm_compile_rescue`` creates start, end, and continuation
  labels, compiles a child rescue ISeq, and records rescue and retry entries.
  The rescue range excludes the else clause and rescue handler itself.
* ``prism_compile.c:pm_compile_ensure`` emits inline cleanup for normal
  completion and creates a child ensure ISeq for unwinding. One ensure may
  have multiple protected ranges.
* ``compile.c:ADD_CATCH_ENTRY`` records symbolic labels and handler identity
  and marks labels as referenced so optimization cannot discard them.
  Prism's ``PUSH_CATCH_ENTRY`` uses this mechanism too.
* ``compile.c:iseq_set_sequence`` resolves label positions and stack depths.
  Compile-time stack adjustments become ``pop`` or ``adjuststack`` where
  needed; they are not dynamic handler-stack operations.
* ``compile.c:iseq_set_exception_table`` converts symbolic entries into
  ``type, start, end, iseq, cont, sp`` records. It derives ``sp`` from the
  continuation label and subtracts one for rescue/break/next, accounting for
  the value supplied when execution resumes.
* Local loop exits usually use direct jumps. ``pm_add_ensure_iseq`` inserts
  cleanup before an exit that crosses ensure scopes. ``add_ensure_range``
  splits each affected protected range around its inlined cleanup, preventing
  cleanup from catching its own exception. Nonlocal exits use ``throw``.

At runtime ``vm_exec_handle_exception`` consults these tables using the
frame PC and restores the recorded stack depth. CRuby tests
``start < pc <= end`` because its saved PC uses the advanced-instruction
convention. Topaz should explicitly use instruction-start PCs and half-open
ranges instead; copying the boundary comparison would be wrong.

Borrow symbolic labels, static depths, and explicit scope boundaries. Do not
copy CRuby's separate handler ISeqs or its stack-depth adjustment convention
into Topaz: their stack protocols differ.

Proposed representation
-----------------------

Store two immutable tables on ``W_CodeObject``:

1. Handler descriptors, indexed by integer ID, with ``-1`` meaning no handler.
   Each descriptor contains a kind (loop, rescue, ensure), target PC, parent
   handler ID, and stack depth relative to the operand-stack base.
2. Sorted, disjoint PC intervals ``[start, end) -> innermost_handler_id``.
   Adjacent intervals with the same ID are coalesced; gaps mean no handler.

Descriptors can share parents. They are compile-time objects, never modified
by a running frame. Mark descriptor fields and finalized table contents
immutable for RPython. Include them in code-object construction and copying.
Use relative depths: the current absolute ``Frame.stackpos`` includes
``len(bytecode.cellvars)`` local slots.

This is a PC-to-static-chain representation rather than a list of overlapping
catches searched afresh for each kind. It preserves Topaz's current innermost
first traversal, including stack cleanup for skipped handlers. A descriptor
can cover multiple disjoint intervals after CFG layout.

Start with an elidable lookup over immutable interval arrays, with an empty
table fast path and binary search for larger tables. Its inputs are only the
code object and instruction-start PC; it must not read a Frame or invoke Ruby.
Do not allocate a dense machine-integer array for every byte unless measured
lookup costs justify that memory tradeoff.

Compiler construction and invariants
------------------------------------

Introduce compiler-only handler descriptors and scope markers. Initially the
existing SETUP/POP structure can supply these markers, but they must disappear
from executable bytecode after lowering. Ordinary POP cleanup is a separate
operation and cannot simply disappear with the marker.

Attach the active handler identity to instructions while constructing the
CFG. Keep handler target blocks reachable through explicit exceptional edges:
today ``Block.post_order`` discovers them through SETUP jump operands, which
will no longer exist. Handler bodies execute under their parent's handler
chain, plus any handlers introduced inside those bodies.

Perform stack analysis before final byte offsets are assigned. The existing
``count_stackdepth`` computes a maximum and treats SETUP targets specially;
it is not a sufficient verifier for static unwind depths. Add a worklist
analysis with explicit normal and exceptional edge stack contracts. Require
consistent depths and handler contexts at reachable joins. If a shared block
requires different contexts, split it or reject the compiler invariant; do
not silently choose one context. Model terminal transfers and unreachable
synthetic expression values explicitly.

Normal and exceptional entries to the existing shared ensure body may have
different payload layouts. Normalize them to a documented layout during
lowering, or represent the permitted alternatives explicitly during analysis;
do not infer a restore depth from whichever path visits the block first.

Finalize in this order: construct scopes and CFG, validate edge contracts,
lower cleanup and markers, lay out reachable blocks, resolve handler and jump
labels, then coalesce PC intervals. Build line tables and optional-argument
entry PCs from that same final layout. Preserve the existing 16-bit bytecode
operand limits and validate any new operands against them.

The central invariant is: at every executable instruction, its static chain
equals the dynamic chain the old implementation would have at that point.
Check this with a temporary untranslated shadow mode before removing the old
chain. Include handler entry, retry, redo, and optional-default entry points.

Runtime dispatch and resuming ensure
-----------------------------------

Use an explicit instruction-start PC for lookup. ``_interpret`` already
receives this PC, whereas individual bytecode methods receive the PC after
decoding operands. Preserve or pass the original PC rather than subtracting
an assumed instruction width. Exceptions returning from a callee belong to
the caller's SEND/YIELD instruction. Keep traceback PCs and handler lookup
PCs conceptually separate.

Replace ``frame.unrollstack`` with a routine taking a static chain head and
an unwind reason. Walk descriptors innermost first, perform the required
cleanup for skipped descriptors, and dispatch to the first matching one.
Leave the frame normally or propagate the existing RPython exception if no
descriptor matches. Preserve matching-parent ``RaiseBreak`` handling in
``handle_bytecode`` and ``Interpreter.run``'s lifetime marking.

Keep ``SuspendedUnroller`` objects for pending exceptional/control-flow state
while an ensure body executes. Their payloads are dynamic: exception, value,
destination interpreter, or throw tag. The change removes FrameBlocks, not
all unwind allocations.

Give each ``END_FINALLY`` an explicit static resume-chain ID during lowering.
After popping the pending payload, resume outside the rescue/ensure that
installed it. Do not look up the original faulting PC again: that would
re-enter the handler just executed. Handler-local rescues and ensures have
already completed when that END is reached.

Nested ensures keep separate pending payloads on the operand stack. A new
exception or return from an ensure supersedes the pending transfer and starts
from the chain active at the new instruction. Stack cleanup must discard
abandoned pending payloads. A frame-global single pending-unwind slot would
be incorrect, including across nested calls and Fiber suspension.

Stack cleanup and Ruby behavior
-------------------------------

Document stack layouts explicitly before changing them. The current base
``FrameBlock`` stores setup depth plus one to retain a suite's result.
``ExceptBlock.handle`` instead restores the original setup depth and pushes
the unroller and exception. ``FinallyBlock`` has distinct normal and unwind
entry protocols. ``LoopBlock`` handles next differently from break.

Preserve those observable results while giving each edge an explicit retained
depth and payload contract. Emit stack cleanup and nil sentinels on normal
paths where POP_BLOCK currently supplies them. Clear discarded slots, as
``Frame.dropvaluesuntil`` does, to avoid retaining Ruby objects unnecessarily.
Never increase stackpos to manufacture values absent on an interrupted path.

For local break and next, initially retain the existing bytecodes and use
static loop descriptors. A next destination is inside the loop's protected
scope; a break destination is outside it. No runtime reinsertion of a loop
descriptor is needed. Preserve ``Interpreter.jump``/``can_enter_jit`` behavior
for backwards transfers, including a next resumed after an ensure.

Keep current nonlocal return/break, lambda/proc behavior, orphan-block errors,
and catch/throw targeting. Rescue still performs Ruby exception matching and
updates ``$!``. Retain the hidden-local ``$!`` save/restore protocol initially,
testing it through nested rescue, ensure, retry, and replacement exceptions.

Redo and retry currently emit POP_BLOCK sequences before jumping. Replace
these with explicit cleanup and correct destination metadata. Preserve
existing compile errors for unsupported crossings of ensure scopes in the
initial migration; expanding Ruby compatibility is a separate change.

JIT considerations
------------------

The interpreter already has bytecode and PC as greens. Static handler lookup
should therefore fold during tracing without adding a JitDriver or another
green. Resolve metadata in helpers taking code/PC, not an opaque helper that
reads virtualizable frame fields. Keep stack mutation visible to the tracer.

Do not unroll arbitrary table searches. A pure lookup can fold for constant
inputs. Inspect traces before deciding whether walking the typically short
static parent chain needs any annotation. Guard exits reconstruct operand
stack payloads and PCs, but no dynamic handler chain.

After validation, remove ``Frame.lastblock`` from initialization and
``_virtualizable_``, delete FrameBlock subclasses and dynamic chain helpers,
and remove executable SETUP/POP opcodes. Measure both metadata memory and
dynamic allocation; lower allocation does not guarantee a throughput win.

Implementation sequence
------------------------

1. Add semantic regression cases and capture a baseline with the current
   binary, source revision, and benchmark configuration recorded.
2. Build immutable metadata alongside existing bytecode and add an
   untranslated shadow checker. Establish stack and scope invariants before
   relying on the tables.
3. Switch unwind dispatch and END_FINALLY resumption to static chains; lower
   normal-path cleanup explicitly. Remove dynamic handler state once all
   control-transfer entry points use metadata. Do not keep two authoritative
   mechanisms in production.
4. Translate, run JIT regression tests, inspect traces, and compare matched
   microbenchmarks and Lobsters runs.
5. Consider direct local jumps and inlined ensure cleanup as a separate
   optimization. They are not prerequisites for eliminating FrameBlocks.

Validation and acceptance
-------------------------

Compiler tests should cover interval boundaries, disjoint ranges for one
descriptor, handler reachability, stack joins, nested handlers, and entry at
optional defaults. Assert that executable bytecode has no SETUP/POP bookkeeping
after migration. Extend the bytecode display used by tests to show metadata.

Behavior tests should cover:

* Normal and exceptional rescue/ensure paths, else exclusions, exceptions in
  exception-class matching, and an exception raised by ensure itself.
* Return/break values, nested ensures, replacement transfers from ensure,
  next/redo in pre- and post-test loops, and retry after nested rescue/loops.
* Exceptions after partial expression evaluation, including calls with
  partially constructed arguments and nonempty operand stacks.
* Nonlocal block return/break, lambdas, escaped procs, catch/throw, recursion,
  Fiber suspension in an ensure, and relevant tracing/backtrace behavior.
* ``$!`` before, during, and after all relevant paths; GC-visible references
  are cleared when pending transfers or stack temporaries are abandoned.

Compare supported Ruby snippets against CRuby. Keep pre-existing semantic
differences separate from regressions introduced by this change. Run compiler,
interpreter, proc, exception, Fiber, and translated JIT suites as appropriate.

Use microbenchmarks for plain loops, unraised rescue, normally completed
ensure, next through ensure, raised exceptions, and nonlocal block exits.
Include a loop whose frame crosses a compiled-loop boundary, reproducing the
escape pattern observed in Integer#times. Add a JIT regression that checks
the relevant surviving allocations and stores, rather than exact unrelated
trace text. Test a guard failure followed by correct exception handling too.

For Lobsters, compare repeated runs with matched warmup and iteration counts,
report per-iteration times, RSS, allocation evidence, trace/bridge counts,
and backend-count-weighted estimates where available. Separate trace-site
counts from estimated runtime traffic. Acceptance requires no FrameBlock
allocation or lastblock stores, correct unwinding after frame materialization,
and no material unexplained performance regression. Report results without
assuming the earlier experimental-driver log predicts current savings.

Alternatives and unresolved questions
-------------------------------------

Preallocating immutable FrameBlocks but retaining a mutable lastblock pointer
is a smaller intermediate experiment. It removes allocations but retains
scope-entry writes and virtualizable state; it is not the intended final design.

A full CRuby-style rewrite into child handler code objects and inlined exit
cleanup would change scope/cell access, traceback behavior, and code size.
Defer it unless same-code handlers prove an obstacle.

Implementation must resolve the existing ensure stack-layout alternatives,
audit tracing-hook exceptions (the line hook currently runs outside the
bytecode exception-catching try), and measure interval-table size on real
code. These are explicit review points, not reasons to infer handler state
from runtime history or broaden compatibility work silently.


Implementation notes
--------------------

``CompilerContext.analyze_unwind`` runs a worklist over the symbolic CFG.
SETUP markers introduce an exceptional edge and a static handler identity;
POP markers leave that identity. The analysis attaches the incoming identity
and operand depth to each reachable instruction. Revisited block entries
must agree on both. Optional-default blocks are additional depth-zero,
empty-chain roots. Terminal transfers stop propagation: synthetic expression
values and other instructions after them are removed. Handler targets remain
reachable through the symbolic SETUP edges until analysis and lowering finish.

The old stack-effect declarations overestimated local constant loads and
constant stores, and miscounted splatted yield. These declarations now match
the interpreter. The verifier checks operand requirements as well as net
stack effects, so a stack-growing operation such as DUP_TOP cannot conceal
an underflow.

Handler depths are the operand depth *before* scope entry, excluding local
slots. Entry contracts, above that saved prefix, are:

* Loop continuation: no payload; break continuation: the break value.
* Rescue: ``[unroller, exception]``. Matching code discards both before
  running the selected clause.
* Ensure normal entry: ``[suite_result, nil, nil]``.
* Ensure unwind entry: ``[nil, unroller, nil]``.

The ensure suite leaves its own result, which DISCARD_TOP removes. END_FINALLY
then removes the last two entry slots. On normal completion this leaves the
suite result. On exceptional completion the remaining dummy result is
removed by subsequent cleanup. END_FINALLY's operand is the resume-chain ID
plus one (zero means the empty chain). Unmatched rescue uses the same runtime
instruction but has a terminal compiler marker, END_RESCUE.

Normal POP lowering emits CLEAR_STACK only when there are values to discard,
and emits the extra nil for normal ensure entry. Loop and rescue exits that
need no cleanup emit no instruction. Every generated operand, including the
late-bound resume ID, receives the existing 16-bit limit check. Jump targets,
line numbers, default-entry PCs and half-open intervals all use the resulting
layout.

The runtime passes instruction-start PCs explicitly to control-transfer
opcodes. Other opcode methods retain their advanced-PC calling convention;
exception dispatch already receives the instruction-start PC from _interpret.
The line hook now runs inside that dispatch's try block. END_FINALLY routes
resumed backward transfers through Interpreter.jump.

Cleanup removes all operands above the saved prefix, including abandoned
pending transfers. Leaving the frame clears the operand stack. Cleanup never
increases stackpos; locals and closure cells are untouched. The existing
hidden-local protocol for $! and the matching-parent RaiseBreak interception
remain in place. No runtime FrameBlock classes or lastblock field remain.

Tests and measurement
---------------------

``tests/test_unwind.py`` covers metadata boundaries, shared parents and
disjoint ranges, copying, optional-default entry points, exceptional-only
reachability, invalid joins and underflows, abandoned references, trace-hook
exceptions, and Ruby transfer behavior. ``tests/jit/test_unwind.py`` repeats
the transfer cases in the translated interpreter (including Fiber suspension)
and checks a materialized-frame/call_assembler path with a late exception.
The compiler test display accepts ``include_unwind=True`` to show descriptors
and intervals alongside executable instructions.

A temporary untranslated checker was run against the original interpreter at
``3c4ca9efadae88be0002720672fbd8a43df3e155``. It independently propagated
symbolic handler identities and compared them with the live linked chain at
each instruction start. The interpreter, modern Ruby, proc and Fiber suites
checked 4,188,777 instruction starts: 346 tests passed and 17 Fiber tests were
skipped by the untranslated runner. The checker is not a production execution
mode.

Compiling 104 files from lib-topaz and lib-ruby produced 3,424 code objects,
275,934 bytecode bytes, 231 descriptors and 250 intervals; 178 code objects
had handlers. On a 64-bit build the descriptor/interval fields and their list
entries account for 17,240 bytes, before object/array headers and the two
additional table references on each code object. This is a structural size
estimate, not an RSS measurement or a dense-per-byte table. The generated C
uses 40-byte descriptors, 32-byte intervals and 16-byte fixed-array headers.
Including both table-array headers and two extra references per code object
gives an estimated 185,440 bytes for this sample, excluding allocator overhead
and any savings from smaller bytecode and exact operand-stack sizes. Empty
tables still have array headers; sharing those is a possible follow-up.

``bench/static_unwind.rb`` measures plain loops, unraised rescue, normal ensure,
next through ensure, raised exceptions, nonlocal return and nested compiled
loops called from Integer#times. It prints each sample separately, using two
warmup samples followed by three measured samples by default. Raised-exception
samples use one hundredth of N and keep the exception in a global so its
allocation remains observable. Next-through-ensure samples use one fiftieth
of N, since that loop stays interpreted in the baseline.

One new transfer regression exposes an existing translated-interpreter bug:
``next`` in an ensure that supersedes a pending exception leaves payloads on
the old loop stack, and the baseline binary segfaults after three iterations.
Static loop continuation explicitly restores the saved depth. This is covered
separately from performance comparisons; the benchmark does not use this
crashing baseline path.

Trace inspection of the first translated version found residual calls to
Interpreter.find_handler, including on empty-chain returns. RPython does not
inline a helper with a loop by default. Marking the short parent-chain walk
``jit.unroll_safe`` restores tracing through it; the interval binary search
remains elidable, without arbitrary search unrolling. The materialized-frame
regression also rejects residual find_handler calls.

A separate existing compatibility difference remains recorded as an expected
failure: returning from ensure while suppressing an exception leaves $! set
to that exception. CRuby restores it; both the baseline and this implementation
leave it set. The rescue hidden-local save/restore protocol is preserved;
changing ensure's errinfo lifetime is outside this handler-storage migration.

For the same library sample, the sum of per-code maximum operand depths fell
from 15,828 to 11,358 slots (the largest fell from 113 to 33). This is a
comparison of frame capacities, not live memory usage: savings depend on which
methods execute and how many frames are live. Performance changes can include
these exact-stack-size savings as well as removal of handler objects.

The final untranslated full-suite run passed 1,758 tests, with 18 skips and
seven pre-existing expected failures. Subsequent additions to the dedicated
unwind suite pass 35 tests, with one untranslated Fiber skip and the errinfo
expected failure described above. All 116 translated JIT tests pass,
including the 18 transfer cases, Fiber suspension, frame materialization and
late guard failure. All 18 transfer expectations were also checked on CRuby.
Eight existing exact-trace fixtures changed only operands/register sets and
PCs; their operation sequences and lengths did not change.

Builds use PyPy 7.3.17-alpha0, RPython revision
``5e27d1d951109270997bb6bc8412d6561a9a623f`` and GCC 12.5.0, with
``--batch -Ojit``. The writable RPython worktree is
``_build/rpython-unwind``. Both the baseline and changed binaries were freshly
translated; existing experimental binaries were not used for comparison.

Matched timing results (2026-10-10)
----------------------------------

Lobsters used 40 warmup and 25 measured iterations per process, twice per
binary, in baseline/new/new/baseline order. Timing runs logged only jit-summary;
the full allocation traces were collected separately. Per-iteration timings,
RSS samples, binary/source hashes, build/test logs and analysis scripts are
retained in ``_build/static-unwind``. ``configuration.json`` records the
configuration; each run directory contains ``benchmark.json`` and ``run.log``.

.. list-table:: Lobsters timing runs
   :header-rows: 1

   * - Run
     - Mean ms/iteration
     - Median ms/iteration
     - Final RSS MiB
     - Compiled loops / bridges
   * - Baseline 1
     - 758.76
     - 706.24
     - 1482.6
     - 3085 / 9896
   * - Static 1
     - 828.02
     - 754.74
     - 1486.4
     - 3107 / 9945
   * - Static 2
     - 773.25
     - 716.73
     - 1459.9
     - 3102 / 9965
   * - Baseline 2
     - 815.24
     - 744.45
     - 1509.5
     - 3123 / 9905

Combined means were 787.00 ms baseline and 800.64 ms static (+1.7%). The first
pair was slower and the reverse-order pair faster; there is no consistent
material regression in these runs, but they do not establish a throughput
improvement. Mean final RSS fell from 1496.1 to 1473.1 MiB. Large pauses and
continued warmup make individual short timing windows variable.

Microbenchmarks used N=50,000,000, two warmup samples and three measured samples
per process, with two processes per binary in the same order. The table gives
medians of six measured samples, in milliseconds. The longer micro runs were
performed separately after the Lobsters timing runs finished.

.. list-table:: Microbenchmarks
   :header-rows: 1

   * - Workload
     - Iterations/sample
     - Baseline ms
     - Static ms
   * - Plain loop
     - 50,000,000
     - 27.144
     - 21.393
   * - Unraised rescue
     - 50,000,000
     - 23.546
     - 13.388
   * - Normal ensure
     - 50,000,000
     - 23.355
     - 23.129
   * - Next through ensure
     - 1,000,000
     - 334.681
     - 0.498
   * - Raised exception, retained in a global
     - 500,000
     - 1.767
     - 1.551
   * - Nonlocal block return
     - 50,000,000
     - 13.188
     - 13.514
   * - Nested compiled loop from Integer#times
     - 50,000,000
     - 2028.561
     - 2061.267

The nonlocal and nested-loop timing ranges overlap between binaries; their
median differences are +2.5% and +1.6%. The large next-through-ensure improvement
comes from reporting the resumed backward jump to the JIT: the baseline loop
stays interpreted. It should not be attributed solely to handler allocation.
``micro-summary.json`` retains sample ranges and individual timings.

Allocation trace results
------------------------

Separate full traces used the same 40+25 iteration workload. The baseline
had 466 surviving handler allocation sites and 5,270 stores to
Frame.lastblock. The static version has zero of either. The baseline also
had 466 stores initializing handler parent links; these disappear too.
The after trace contains no FrameBlock fields, lastblock accesses or residual
Interpreter.find_handler calls.

.. list-table:: Optimized trace evidence
   :header-rows: 1

   * - Metric
     - Baseline
     - Static
   * - Logged loop/entry sections
     - 2561
     - 2583
   * - Logged bridge sections
     - 9905
     - 9950
   * - All allocation sites
     - 166193
     - 165280
   * - Handler allocation sites
     - 466
     - 0
   * - Frame.lastblock store sites
     - 5270
     - 0
   * - Backend-weighted handler allocation estimate
     - 2858285
     - 0
   * - Backend-weighted Frame.lastblock store estimate
     - 22061096
     - 0
   * - Backend-weighted all-allocation estimate
     - 925535776
     - 952484483

Allocation class names are not printed by this backend's SizeDescr. Surviving
old handlers are counted by their once-only FrameBlock.stackdepth
initialization. Weighted estimates use the current entry/label/bridge counter;
they do not account precisely for exits at individual guards, and missing
counters contribute zero. These are estimates of trace traffic, not measured
GC allocation counts. Overall estimated allocation traffic increases in this
capture despite removal of handler objects, so no overall allocation or
throughput reduction is claimed. The acceptance evidence is the elimination
of handler state, correct transfers after materialization and guard failure,
and no consistent material slowdown in the repeated timing runs.
