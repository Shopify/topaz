from ..base import BaseTopazTest


class TestMutexObject(BaseTopazTest):
    def test_name(self, space):
        w_res = space.execute("return Thread::Mutex.name, Mutex.equal?(Thread::Mutex)")
        assert self.unwrap(space, w_res) == ["Thread::Mutex", True]

    def test_lock_unlock(self, space):
        w_res = space.execute("""
        m = Mutex.new
        r = [m.locked?, m.owned?]
        r << m.lock.equal?(m)
        r << m.locked? << m.owned?
        r << m.try_lock
        r << m.unlock.equal?(m)
        r << m.locked?
        r << m.try_lock << m.locked?
        m.unlock
        return r
        """)
        assert self.unwrap(space, w_res) == [False, False, True, True, True, False, True, False, True, True]

    def test_errors(self, space):
        with self.raises(space, "ThreadError", "deadlock; recursive locking"):
            space.execute("m = Mutex.new; m.lock; m.lock")
        with self.raises(space, "ThreadError", "Attempt to unlock a mutex which is not locked"):
            space.execute("Mutex.new.unlock")
        with self.raises(space, "ThreadError", "must be called with a block"):
            space.execute("Mutex.new.synchronize")

    def test_synchronize(self, space):
        w_res = space.execute("""
        m = Mutex.new
        r = []
        v = m.synchronize { r << m.locked?; 42 }
        r << v << m.locked?
        begin
          m.synchronize { raise "boom" }
        rescue => e
          r << e.message << m.locked?
        end
        return r
        """)
        assert self.unwrap(space, w_res) == [True, 42, False, "boom", False]

    def test_sleep(self, space):
        w_res = space.execute("""
        m = Mutex.new
        m.lock
        m.sleep(0.001)
        return m.locked?
        """)
        assert w_res is space.w_true
        with self.raises(space, "ThreadError", "No live threads left. Deadlock?"):
            space.execute("m = Mutex.new; m.lock; m.sleep")

