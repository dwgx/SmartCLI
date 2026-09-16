# Executable design models — E2 only

`contracts.py` is an injected, non-threaded design model, not SmartCLI code.
It has no native transport, worker thread, mutex, condition variable or socket.
It tests byte-offset accounting, explicit progress/ACK/verification separation,
bounded payload admission and ordering, and close-request versus EOF semantics.

A `BudgetBuffer.begin_close()` request does **not** forbid final transport output
or imply process exit. Output remains admissible until `signal_eof()`, within
the same capacity. It does not model a native blocking read, cancellation wake,
process-tree termination, OS memory use or fairness. Those remain separate tests.

The write reference bounds injected attempts; its callback deadline is not a way
to preempt a blocking OS write. It is not an actor or a production patch. The
local worker may choose a different implementation that satisfies the contracts.
