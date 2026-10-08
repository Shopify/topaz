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


class W_MonitorObject(W_Object):
    """Monitor, MRI's reentrant lock (ext/monitor/monitor.c). With a single
    thread the owner is either nobody or the current thread, so it is a flag."""
    classdef = ClassDef("Monitor", W_Object.classdef)

    def __init__(self, space, klass=None):
        W_Object.__init__(self, space, klass)
        self.locked = False
        self.owned = False
        self.count = 0

    def __deepcopy__(self, memo):
        obj = super(W_MonitorObject, self).__deepcopy__(memo)
        obj.locked = self.locked
        obj.owned = self.owned
        obj.count = self.count
        return obj

    @classdef.singleton_method("allocate")
    def method_allocate(self, space):
        return W_MonitorObject(space, self)

    def enter(self, space):
        if not self.owned:
            if self.locked:
                raise space.error(space.getclassfor(W_ThreadError), "deadlock; recursive locking")
            self.locked = True
            self.owned = True
            self.count = 0
        self.count += 1

    def check_owner(self, space):
        if not self.owned:
            raise space.error(space.getclassfor(W_ThreadError), "current fiber not owner")

    def exit(self, space):
        self.check_owner(space)
        if self.count <= 0:
            raise space.error(space.getclassfor(W_ThreadError), "monitor_exit: count:%d" % self.count)
        self.count -= 1
        if self.count == 0:
            self.owned = False
            self.locked = False

    @classdef.method("try_enter")
    def method_try_enter(self, space):
        if not self.owned:
            if self.locked:
                return space.w_false
            self.locked = True
            self.owned = True
            self.count = 0
        self.count += 1
        return space.w_true

    @classdef.method("enter")
    def method_enter(self, space):
        self.enter(space)
        return space.w_nil

    @classdef.method("exit")
    def method_exit(self, space):
        self.exit(space)
        return space.w_nil

    @classdef.method("mon_check_owner")
    def method_mon_check_owner(self, space):
        self.check_owner(space)
        return space.w_nil

    @classdef.method("mon_locked?")
    def method_mon_lockedp(self, space):
        return space.newbool(self.locked)

    @classdef.method("mon_owned?")
    def method_mon_ownedp(self, space):
        return space.newbool(self.locked and self.owned)

    @classdef.method("synchronize")
    def method_synchronize(self, space, block):
        if block is None:
            raise space.error(space.w_LocalJumpError, "no block given")
        self.enter(space)
        try:
            return space.invoke_block(block, [])
        finally:
            self.exit(space)

    @classdef.method("wait_for_cond")
    def method_wait_for_cond(self, space, w_cond, w_timeout):
        count = self.count
        self.owned = False
        self.count = 0
        try:
            # The mutex handed to the condition variable is this monitor's
            # lock; Topaz's ConditionVariable only needs something that
            # answers sleep, so pass a Mutex standing in for it.
            w_mutex = W_MutexObject(space)
            w_mutex.locked = self.locked
            self.locked = False
            try:
                space.send(w_cond, "wait", [w_mutex, w_timeout])
            finally:
                self.locked = True
        finally:
            self.owned = True
            self.count = count
        return space.w_true
