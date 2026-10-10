Frame control metadata
======================

Ruby frames and builtin frames share ``BaseFrame`` bookkeeping: a virtual
reference to the caller and a packed ``flags`` word. The low two bits store
Ruby method visibility, the next bit records whether the frame has escaped,
and the remaining bits hold the caller's bytecode position. Updates preserve
the other parts of the word.

``ExecutionContext.enter`` records the caller position from the execution
context before installing the new top-frame reference. Backtrace construction
reads that position from the child frame to locate the call in its caller.
The position follows the existing instruction-decoding convention:
``Frame.get_lineno`` subtracts one before indexing the caller's line table.
The current frame's own ``last_instr`` remains separate and virtualizable.

The initial execution position is not retained in the frame. Argument setup
returns the entry PC selected by the number of supplied optional positional
arguments. ``ObjectSpace.execute_frame`` and ``Interpreter.run`` pass it to
the interpreter portal, where PC is a JIT green. Calls with no default-argument
prologue, including the fast argument path, start at zero. Block, lambda, and
``define_method`` invocation propagate the result of their argument setup in
the same way.

Fiber startup prepares arguments before switching stacks. Its entry PC travels
through the existing ``GlobalState`` handoff alongside the object space. The
new stack's callback saves it locally before clearing that state. The handoff
is published after argument coercion, which may itself resume another Fiber.
Later resumes continue the suspended interpreter and do not rerun argument
setup or the default prologue. No entry-PC field is needed on each Fiber.

For the ancestor context shared by frames and blocks, see :doc:`super-lookup`.
