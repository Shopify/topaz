Reducing per-frame state
========================

This document describes candidates for reducing the fields carried by every
``Frame``: the owner occurrence used by ``super``, regexp match state, and
nonlocal control-flow destinations.

The objective is to reduce allocation and retained memory when frames
materialize, without introducing compensating allocations on ordinary calls.
The JIT can already eliminate unused state in virtual frames, so a smaller
Python class alone is not evidence of an improvement.

Current representation and priorities
-------------------------------------

The remaining fields to investigate in ``topaz/frame.py`` are:

* ``super_occurrence``: the occurrence of the owner that supplied this call.
* ``regexp_match_cell``: shared storage for the lexical regexp match state.
* ``parent_interp`` and ``top_parent_interp``: captured interpreter identities
  used for nonlocal break and return, respectively. These are not references
  to parent frames or a dynamic caller chain.

Investigate folding ``super_occurrence`` into shared metadata next, without
per-call allocation. Defer regexp state until there is a broader environment
design, and leave the interpreter destination references unchanged. These
changes do not depend on adopting all of CRuby's frame representation.

CRuby reference
---------------

The reference checkout is Ruby revision
``334b4ffa7fa75c5e347799a7609c252abe68df30``. Its control frame contains PC,
stack pointer, instruction sequence, receiver, environment pointer, block
code, and JIT return address, plus an optional debug field. Locals and
environment bookkeeping occupy additional VM stack storage; control-frame
size is not the whole activation cost.

The environment has slots for flags, a block handler or enclosing environment,
and method-entry or lexical-scope metadata. Some of those slots can instead
refer to a wrapper containing additional state. This sharing of storage is
central to the comparisons below. See `CRuby frame and environment layout`_.

Super owner occurrence
----------------------

CRuby obtains a callable method entry through the environment. The entry
contains ``owner`` and ``defined_class``; its method definition contains
``original_id``. Super lookup uses the original name and begins after the
appropriate ancestor position represented by ``defined_class``. Included
modules have ICLASS nodes in the ancestor chain, so that position need not be
encoded as a separate numeric occurrence on each frame. See `CRuby method
entries`_ and ``vm_search_super_method`` in `CRuby instruction helpers`_.

``super_occurrence`` identifies which occurrence of the owner supplied this
call. Folding it into ``SuperContext`` would remove another field from frames
and procs. A function alone does not identify the occurrence: the same
function can participate in different lookup paths.

Explore occurrence-specific variants of the existing context. Ordinary calls
should reuse a context with occurrence zero. Nonzero occurrences could use
cached variants keyed by the base context and occurrence, selected when
entering the method and retained by blocks it creates. Keep the variants
immutable so a later call cannot change an escaped block's destination.

Alternatively, an existing resolved-method or lookup-cache entry could own
the context variant. Avoid allocating a fresh context on every call. Audit
both the normal call path and the fast argument path in
``ObjectSpace.send_valuestack``, as well as method objects, ``define_method``,
and block creation and invocation.

Define how context remains valid across method redefinition, aliasing,
include/prepend changes, and calls through previously obtained method objects.
Cache invalidation must preserve the intended lookup semantics, rather than
merely retain a convenient old ancestor position. Preserve lexical ownership
when a block escapes and later executes ``super``.

Validation must cover inheritance, aliases, singleton methods, include and
prepend chains, repeated occurrences of a module, bound and unbound methods,
explicit and implicit super arguments, ``defined?(super)``, and nested or
escaped blocks from ``define_method``. Trace ordinary calls as well as super
calls; eliminating the occurrence field is useful only if the replacement
does not add routine allocations or frame forcing.

Regexp match state
------------------

CRuby lazily creates a ``vm_svar`` object containing backreference state
(``$~``), last-line state (``$_``), and other special variables. It reuses the
environment slot normally holding method-entry or lexical-scope metadata;
the wrapper preserves that original metadata. Blocks locate the applicable
state through their environment chain. Reading absent special-variable state
does not allocate it. See `CRuby special-variable storage`_ and
``lep_svar_get``/``lep_svar_set`` in `CRuby instruction helpers`_.

Topaz already creates its match cell lazily, but every frame and proc carries
a reference to it. ``BUILD_BLOCK`` obtains the shared cell even if no match
has occurred, so a later match in the enclosing scope remains visible to the
block. Removing that eager capture without another shared anchor is incorrect.

Evaluate whether a shared lexical environment or optional scope-state wrapper
could hold the cell without a dedicated field on every frame. Specify how
blocks created before the first match discover later updates. Do not rely
solely on explicit regexp syntax: native methods and callbacks can access or
update the state indirectly. Account for the wrapper's allocation, lifetime,
indirections, and any unrelated data it keeps alive.

Validation must cover matches before and after block creation, escaped blocks,
nested methods and blocks, ``$~`` assignment, derived captures such as ``$1``
and ``$&``, regexp callbacks, Enumerable methods acting on a block's behalf,
and Fiber behavior. Keep this separate from method-context consolidation until
the ownership and lifetime rules are explicit.

Activation identity and nonlocal transfers
------------------------------------------

CRuby captures an environment pointer with a block. A nonlocal return walks
the lexical environments and searches active control frames for the matching
destination, respecting lambda boundaries. Break resolution also checks the
matching break catch-table entry and current PC. Missing destinations are
rejected as local-jump errors. A pending transfer stores the resolved control
frame; there is no separate activation token with a finished flag. Escaping
environments are moved to heap storage without retaining the whole control
frame. See ``vm_throw_start`` in `CRuby instruction helpers`_ and
``vm_make_env_each`` in `CRuby environment escape handling`_.

Topaz uses a separate ``Interpreter`` object for each invocation. Its identity
names that activation, and its ``finished`` flag records its lifetime. The
object does not retain the frame. Both ``Frame`` and ``W_ProcObject`` carry
the following references:

* ``parent_interp`` identifies the invocation that created the block. During
  ``BUILD_BLOCK``, the proc captures the currently executing interpreter.
  Ordinary block invocation copies this reference into the new frame.
  ``RAISE_BREAK`` checks its ``finished`` flag to reject an orphan break and
  carries it in ``RaiseBreak`` or a pending ``RaiseBreakValue``. The matching
  interpreter intercepts the transfer in ``handle_bytecode``; proc and lambda
  calls also apply their existing break-handling rules.
* ``top_parent_interp`` identifies the lexical nonlocal-return destination.
  ``BUILD_BLOCK`` captures ``frame.top_parent_interp or self``, so blocks
  nested in ordinary blocks inherit the enclosing return destination.
  ``RAISE_RETURN`` carries that reference in ``RaiseReturn`` or a pending
  ``RaiseReturnValue``. ``Interpreter.interpret`` catches the transfer only
  when its destination is that interpreter instance.

A lambda invocation supplies its own interpreter as ``top_parent_interp``.
Returns from the lambda body, or blocks it creates, therefore end at that
invocation. A block merely forwarded through the lambda retains its original
destination. Distinct interpreter instances distinguish recursive activations
of the same bytecode. Ordinary method frames start with both captured
references set to ``None``; their own interpreter is supplied by execution,
not stored in another frame field.

``Interpreter.run`` sets ``finished`` on exit in a ``finally`` outside the
JIT portal, including exceptional exit. The JIT can virtualize an interpreter
when its identity does not escape. If a block retains it, the captured object
is small and does not keep the defining frame alive.

Keep this representation for now. The lazy activation-token experiment was
abandoned: it added a field to every frame, and reading that virtualizable
field during finalization introduced synchronization after compiled calls.
Removing an interpreter allocation did not establish an overall benefit.

Do not replace interpreter references with defining-frame references. A
CRuby-like alternative would first need an environment identity that maps
reliably to a live activation, including recursive invocations of the same
bytecode. It must
also define stack-search behavior across compiled calls and Fibers. Searching
Topaz's virtual frame chain may force frames, which could outweigh any saved
fields. Frame-layout specialization is another possibility, but its effect on
RPython virtualizable layouts needs investigation before implementation.

Validation must preserve lexical return targets, lambda-local returns,
forwarded blocks, orphan breaks, nested ensures, replacement transfers,
recursion, and Fiber suspension. Check destination capture after a guard
failure, lifetime marking after compiled returns, and whether escaping
closures keep defining frames virtual.

Experiment and acceptance process
---------------------------------

Make one representation change at a time. Keep a baseline binary and matched
workloads, run the relevant semantic tests, then translate and inspect optimized
traces. Include plain calls across compiled-loop boundaries, calls using the
feature being moved, escaping blocks, and a guard failure after warmup.

For each change, account for the entire storage cost: generated frame layout,
locals/cell arrays, code metadata, shared cache entries, optional objects, and
boxed values. Distinguish allocation sites in traces from executed allocations.
Check for added residual calls, guards, and frame materialization, not just
the disappearance of a named field.

Accept a change when its semantics are preserved and its common-case saving
survives those costs. Keep benchmark logs and trace captures as experiment
artifacts rather than adding historical measurement tables to this document.
Once a change is adopted, document how its representation works in the
implementation documentation.

.. _CRuby frame and environment layout: https://github.com/ruby/ruby/blob/334b4ffa7fa75c5e347799a7609c252abe68df30/vm_core.h
.. _CRuby method entries: https://github.com/ruby/ruby/blob/334b4ffa7fa75c5e347799a7609c252abe68df30/method.h
.. _CRuby instruction helpers: https://github.com/ruby/ruby/blob/334b4ffa7fa75c5e347799a7609c252abe68df30/vm_insnhelper.c
.. _CRuby special-variable storage: https://github.com/ruby/ruby/blob/334b4ffa7fa75c5e347799a7609c252abe68df30/internal/imemo.h
.. _CRuby environment escape handling: https://github.com/ruby/ruby/blob/334b4ffa7fa75c5e347799a7609c252abe68df30/vm.c
