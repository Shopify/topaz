Super lookup and ancestor identity
==================================

A ``super`` call resumes after the ancestor occurrence that supplied the
running method. The module alone does not identify that position: a module
can occur more than once through include, prepend, and inheritance. Nor is
its occurrence number stable when Ruby code changes the ancestor chain
while a method is running or after it has returned a block.

Ancestor entries
----------------

Each module or class has an ``origin_entry`` for its own method table, plus
``included_entries`` and ``prepended_entries`` arrays. An ``AncestorEntry``
identifies one occurrence and references its module and the class or module
whose local chain contains it. Superclasses contribute
their existing entries to a subclass's chain.

Includes and prepends insert new entries without replacing existing ones.
Propagation of later module changes follows the same rule, including when
that module occurs several times. Copying a module or singleton class creates
independent local entries. The parallel module arrays remain available to
ordinary method lookup and the Ruby ``ancestors`` API.

Entries do not freeze a chain or contain immutable next pointers. Super lookup
finds the captured entry by identity in its owning ancestor chain and searches
after it. Changing the receiver with ``instance_exec`` does not change this
destination. Inserting a module before that entry cannot move the
starting point to a different occurrence. Inserting a module after it remains
visible, as do method redefinitions.

Capturing the entry
-------------------

``SuperContext`` contains the owner, the ancestor entry, and an optional method
name override used by ``define_method``. Ordinary Ruby methods obtain the
original name from their bytecode. Aliases preserve the function's original
super metadata: invoking an alias resolves the original owner's occurrence
at that time, while a block from an executed alias retains the resolved entry.

Methods defined on classes use their owner's origin context directly. Methods
defined on modules resolve a context for the appropriate occurrence in the
receiver's chain before running the body. This happens on both ordinary calls and the fast
argument path in ``send_valuestack``. A super call passes the next selected
entry explicitly to the callee, distinguishing repeated occurrences.

Frames hold one context reference. Blocks capture that same reference; block
copies and invocations retain it. They need neither a numeric occurrence nor
a reference to the defining frame. ``define_method`` selects the installed
method's context when invoking its block body.

A bound ``Method`` stores the selected entry when it is bound and preserves
it across later ancestor changes. An ``UnboundMethod`` selects an entry in
the receiver's current chain when it is bound, including after an unbind/bind
round trip. This distinction follows CRuby's binding behavior.

Sharing, invalidation, and lifetime
----------------------------------

Contexts are cached on ancestor entries: one for ordinary methods, and named
contexts for ``define_method``. Calls and captured blocks share these immutable
objects. Filling a context cache can allocate; subsequent calls reuse it.

Each receiving class caches resolution from base contexts to occurrence
contexts. Its version tag and the global method-cache state invalidate this
cache after relevant changes. Super lookup itself is elidable with those same
version inputs, allowing the JIT to fold the ancestor walk for known classes
and contexts. Invalidation changes future lookup results without changing the
entry identities retained by active calls, blocks, or bound methods.

The included module does not cache contexts for its including classes.
Otherwise a long-lived module could retain anonymous classes indefinitely.
Occurrence contexts belong to the entries in the including class, and the
existing descendant registry uses weak references.

The representation adds shared entry and cache storage per class/module and
one entry reference per bound method. It does not allocate an entry or a new
context on each ordinary method invocation. Tests cover mutation during
execution, escaped blocks, binding, repeated modules, later propagation,
context reuse, and collection of including classes.
