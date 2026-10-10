Static unwind tables for Topaz
==============================

Topaz stores loop, rescue, and ensure scopes as immutable metadata on each
``W_CodeObject``. When an exception or control transfer occurs, the interpreter
uses the instruction's byte offset to recover the active handler chain.
Ordinary execution does not allocate handler objects or maintain a handler
pointer on the frame. ``Frame`` has no ``lastblock`` field.

Rescue and ensure bodies execute in the same code object as the protected
body. Pending exceptions, return values, and other transfers still use
``SuspendedUnroller`` objects; the tables describe where to handle a transfer,
not its dynamic payload.

Code-object metadata
--------------------

``topaz/objects/codeobject.py`` defines two tables:

* ``unwind_handlers`` contains ``UnwindHandler`` descriptors. Each has a
  ``kind`` (``LOOP``, ``RESCUE``, or ``ENSURE``), ``target_pc``, ``parent``
  handler ID, and ``stackdepth``. IDs are indices into this table; ``-1``
  denotes the empty chain.
* ``unwind_intervals`` contains sorted, disjoint ``UnwindInterval`` records:
  ``[start, end) -> handler``. The handler is the innermost active descriptor.
  Adjacent intervals with the same handler are coalesced. Gaps have no handler.

Descriptors can share parents, and one descriptor can cover several disjoint
intervals after block layout. Handler bodies run under their parent's chain,
plus any scopes introduced inside those bodies. In particular, a rescue does
not catch exceptions raised by its own matching code, clauses, or else body.

Depths count operand slots, excluding local slots. The corresponding absolute
frame position is ``len(bytecode.cellvars) + handler.stackdepth``. Descriptor
fields and table contents are immutable to RPython, and code-object deep copies
share the finalized tables.

``W_CodeObject.handler_at(pc)`` performs an elidable binary search and returns
an ID or ``-1``. It reads only the code object's metadata. PCs are byte offsets
at the **start** of instructions, and interval ends are exclusive.

Compiler analysis and lowering
------------------------------

The AST compiler in ``topaz/ast.py`` emits symbolic ``SETUP_LOOP``,
``SETUP_EXCEPT``, ``SETUP_FINALLY``, and ``POP_BLOCK`` markers. These are
compiler-only operations defined in ``topaz/consts.py``; they never appear in
executable bytecode. Their targets also keep handler blocks reachable during
``Block.post_order`` traversal, including handlers reached only by unwinding.

``CompilerContext.create_bytecode`` in ``topaz/astcompiler.py`` finalizes the
code in three stages:

1. ``analyze_unwind`` walks the control-flow graph with a worklist. Its state
   is the incoming operand depth and active handler ID. SETUP markers create
   descriptors and exceptional edges; POP markers leave a scope. The analysis
   annotates each reachable instruction with its state and computes
   ``max_stackdepth``.
2. ``lower_unwind`` removes scope markers and unreachable instructions,
   introduces explicit stack cleanup where needed, and encodes handler
   resumption in ``END_FINALLY`` operands.
3. ``get_code_lineno_table`` assigns byte offsets and patches jumps;
   ``build_unwind_tables`` resolves handler targets and coalesces intervals.
   Line tables and optional-argument entry PCs use this same final layout.

Every reachable join must agree on both depth and handler context; otherwise
compilation raises ``CompilerError``. The verifier checks required operands
as well as net stack effects, so an operation such as ``DUP_TOP`` cannot hide
an underflow by increasing the depth. Optional positional-default entry
blocks are additional roots with depth zero and no active handler.

Exceptional edges have explicit stack contracts: loop break targets receive
one value above the saved prefix, rescue targets receive two slots, and
ensure targets receive three. ``CONTINUE_LOOP`` targets instead receive the
loop's saved depth and retain the loop in their static chain. Terminal
transfers stop propagation, so synthetic expression values after them are
removed during lowering.

POP lowering retains at most the saved prefix for loops, or that prefix plus
one result for rescue and ensure. It emits ``CLEAR_STACK`` only when values
need discarding. Normal ensure entry also receives a nil sentinel from
lowering; the AST supplies the other nil. The compiler checks generated
operands, including late-bound resume IDs and handler targets, against the
16-bit bytecode limit.

Runtime dispatch
----------------

``Interpreter._interpret`` keeps the instruction-start PC while dispatching
an opcode. Exceptions raised by a callee are therefore handled at the caller's
SEND or YIELD instruction. Line tracing runs inside the same exception-catching
``try``, so a Ruby exception raised by the trace hook uses that instruction's
handler chain too.

Most opcode methods receive the PC after operand decoding. ``RETURN``,
``RAISE_RETURN``, ``RAISE_BREAK``, ``BREAK_LOOP``, and ``CONTINUE_LOOP`` receive
the instruction-start PC explicitly because they initiate an unwind lookup.
The advanced PC used by calls and backtraces is separate from handler lookup.

``Interpreter.find_handler`` walks the static parent chain from innermost to
outermost. An ensure accepts every transfer; a rescue accepts an
``ApplicationException``; a loop accepts local ``ContinueLoop`` and
``BreakLoop`` transfers. Skipped handlers cause cleanup to their saved depth.
If no handler accepts the transfer, all operands are cleared and the transfer
leaves the frame through the existing return/exception machinery.

``enter_handler`` restores the selected handler's saved prefix and installs
its payload. ``resume_unwind`` combines lookup and entry for a pending
``SuspendedUnroller``; if the chain is exhausted, the unroller's
``nomoreblocks`` method propagates it.

Nonlocal returns and breaks retain their destination interpreter, and throws
retain their tag and value. ``handle_bytecode`` still intercepts a
``RaiseBreak`` whose parent is the current interpreter. ``Interpreter.run``
marks an interpreter finished outside the JIT portal, preserving the lifetime
check for breaks from orphaned blocks.

Stack layouts and ensure resumption
-----------------------------------

Each handler's ``stackdepth`` records the operand depth before entering its
scope. The following payloads sit above that saved prefix:

.. list-table:: Handler entry payloads
   :header-rows: 1

   * - Entry
     - Payload
   * - Loop next
     - No payload; resume at the transfer's target PC
   * - Loop break
     - ``[break_value]``
   * - Rescue
     - ``[unroller, exception]``
   * - Ensure, normal completion
     - ``[suite_result, nil, nil]``
   * - Ensure, unwinding
     - ``[nil, unroller, nil]``

Rescue entry sets ``$!`` to the exception. Matching code discards the rescue
payload before running the selected clause. If no clause matches, the
compiler's terminal ``END_RESCUE`` marker lowers to ``END_FINALLY`` and resumes
the pending exception under the parent chain.

Normal and exceptional ensure entries have the same size. The ensure body
leaves its own result, which ``DISCARD_TOP`` removes. ``END_FINALLY`` then pops
the last two entry slots. With no pending unroller, execution continues with
the original suite result still on the stack. With an unroller, it resumes
unwinding; subsequent cleanup removes the unused dummy result.

``END_FINALLY`` carries the static resume-chain ID plus one: operand zero
means the empty chain. Resumption starts outside the handler that installed
the payload. Looking up the original faulting PC again would re-enter that
handler, so resumption uses the explicit operand instead.

Nested ensures keep independent pending payloads on the operand stack. A new
exception or return inside an ensure supersedes the pending transfer and
starts from the chain active at the new instruction. Cleanup discards any
abandoned payloads. Keeping these on the frame's stack also preserves them
across nested calls and Fiber suspension.

``clear_stack`` delegates to ``Frame.dropvaluesuntil``, which clears discarded
references. It never increases ``stackpos``: an interrupted instruction may
already have consumed some operands. Locals and closure cells are untouched.

Loop exits, redo, and retry
---------------------------

Local break and next use static loop descriptors. Break restores the saved
prefix, supplies the break value, and leaves the loop scope. Next discards its
value, restores the prefix, and resumes inside the loop scope. The destination
PC's metadata supplies the active chain; no runtime descriptor is reinserted.

``CONTINUE_LOOP`` and resumed transfers from ``END_FINALLY`` route backward
jumps through ``Interpreter.jump``. This reports the backedge to the JIT even
when a next passes through an ensure.

Redo and retry emit compiler-only POP markers followed by a jump. Lowering
turns any necessary cleanup into ``CLEAR_STACK``, and the destination carries
its own static chain. Retry also restores the saved ``$!`` before re-entering
the protected body. Crossings of ensure scopes that the AST compiler does not
support raise a compile error.

JIT behavior
------------

The code object and PC are already JIT greens. Immutable interval lookup can
therefore fold during tracing without additional driver state.
``handler_at`` is ``jit.elidable``; the binary search is not unrolled.
``find_handler`` is ``jit.unroll_safe`` so tracing follows the short parent
chain instead of leaving a residual call that can force frame materialization.
Stack mutation stays visible to the tracer.

Guard exits reconstruct the PC and operand-stack payloads. There is no dynamic
handler chain to reconstruct or store in a materialized frame. Frames also
omit the pointer-sized ``lastblock`` field. Pending transfer objects remain
dynamic and can still allocate when they are not virtualized.

Inspecting bytecode
-------------------

``code.dis()`` is an untranslated Python debugging helper on ``W_CodeObject``.
It prints source lines, byte offsets, target markers, opcode operands and
their meanings, followed by ``ExceptionTable:`` and ``Handlers:`` sections
when unwind intervals are present. It writes to stdout by default::

    code = space.compile('begin; 1; ensure; 2; end', None)
    code.dis()
    code.dis(depth=0)       # only this code object
    code.dis(file=stream)   # redirect output

Nested code objects are displayed recursively by default. ``depth`` limits
that recursion. The method is not exposed as a Ruby method.

The exception-table format follows CPython's style: ``start to last -> target
[depth]``, with Topaz's handler kind, ID, and parent appended. The displayed end
is the offset of the last protected instruction, **inclusive**, rather than
the exclusive byte boundary stored internally. Instructions have variable
widths, so this is not necessarily ``end - 1``. The separate handler listing
includes parents that have no interval of their own.

The compiler test helper ``TestCompiler.get_lines(code, include_unwind=True)``
also displays descriptors and intervals. That compact assertion format shows
the actual half-open ranges.

Tests and known limitations
---------------------------

``tests/test_unwind.py`` covers interval boundaries, shared parents, disjoint
ranges, copying, optional-default entry points, exceptional-only reachability,
invalid joins and underflows, discarded references, trace-hook exceptions,
and Ruby transfer behavior. Its semantic cases exercise nested ensures,
replacement transfers, partial expressions, rescue matching and else
exclusions, loop exits, retry, nonlocal returns and breaks, catch/throw,
recursion, lambdas, and Fiber suspension.

``tests/jit/test_unwind.py`` repeats the transfer cases in the translated
interpreter. Its materialized-frame case crosses a compiled-loop boundary and
handles a late exception after a guard failure. Trace checks reject dynamic
handler fields, ``lastblock`` accesses, and residual ``find_handler`` calls.
``tests/test_compiler.py`` checks executable bytecode, and
``tests/test_disassembler.py`` checks the disassembly format, operand decoding,
constant annotations, recursive output, and unwind-table display.

Rescue uses a hidden local to save and restore ``$!``. One compatibility
limitation remains: returning from ensure while suppressing an exception
leaves ``$!`` set to that exception, rather than restoring it. This is recorded
as an expected failure in ``tests/test_unwind.py``. Static handler tables do
not change that ensure exception-state lifetime behavior.
