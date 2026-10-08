from topaz.module import ClassDef
from topaz.objects.exceptionobject import W_ThreadError
from topaz.objects.objectobject import W_Object


class W_MutexObject(W_Object):
    """Thread::Mutex. Topaz runs a single Ruby thread, so a mutex is just a
    locked flag plus the ThreadError messages MRI raises on misuse."""
    classdef = ClassDef("Thread::Mutex", W_Object.classdef)

    def __init__(self, space, klass=None):
        W_Object.__init__(self, space, klass)
        self.locked = False

    def __deepcopy__(self, memo):
        obj = super(W_MutexObject, self).__deepcopy__(memo)
        obj.locked = self.locked
        return obj

    @classdef.singleton_method("allocate")
    def method_allocate(self, space):
        return W_MutexObject(space, self)

    def lock(self, space):
        if self.locked:
            raise space.error(space.getclassfor(W_ThreadError), "deadlock; recursive locking")
        self.locked = True

    def unlock(self, space):
        if not self.locked:
            raise space.error(space.getclassfor(W_ThreadError), "Attempt to unlock a mutex which is not locked")
        self.locked = False

    @classdef.method("lock")
    def method_lock(self, space):
        self.lock(space)
        return self

    @classdef.method("try_lock")
    def method_try_lock(self, space):
        if self.locked:
            return space.w_false
        self.locked = True
        return space.w_true

    @classdef.method("unlock")
    def method_unlock(self, space):
        self.unlock(space)
        return self

    @classdef.method("locked?")
    def method_lockedp(self, space):
        return space.newbool(self.locked)

    @classdef.method("owned?")
    def method_ownedp(self, space):
        return space.newbool(self.locked)

    @classdef.method("synchronize")
    def method_synchronize(self, space, block):
        if block is None:
            raise space.error(space.getclassfor(W_ThreadError), "must be called with a block")
        self.lock(space)
        try:
            return space.invoke_block(block, [])
        finally:
            self.unlock(space)

    @classdef.method("sleep")
    def method_sleep(self, space, w_timeout=None):
        self.unlock(space)
        try:
            if w_timeout is None or w_timeout is space.w_nil:
                raise space.error(space.getclassfor(W_ThreadError), "No live threads left. Deadlock?")
            # Nothing can wake a single-threaded sleeper, so it always times
            # out, which MRI reports as nil.
            space.send(space.w_kernel, "sleep", [w_timeout])
            return space.w_nil
        finally:
            self.lock(space)

