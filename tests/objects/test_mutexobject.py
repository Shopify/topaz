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


class TestMonitorObject(BaseTopazTest):
    def test_enter_exit(self, space):
        w_res = space.execute("""
        require 'monitor'
        m = Monitor.new
        r = [m.mon_locked?, m.mon_owned?]
        m.enter
        m.mon_enter
        r << m.mon_locked? << m.mon_owned? << m.try_enter
        m.exit
        r << m.mon_locked?
        m.mon_exit
        r << m.mon_locked?
        m.exit
        r << m.mon_locked?
        return r
        """)
        assert self.unwrap(space, w_res) == [False, False, True, True, True, True, True, False]

    def test_errors(self, space):
        with self.raises(space, "ThreadError", "current fiber not owner"):
            space.execute("require 'monitor'; Monitor.new.exit")
        with self.raises(space, "ThreadError", "current fiber not owner"):
            space.execute("require 'monitor'; Monitor.new.mon_check_owner")

    def test_synchronize(self, space):
        w_res = space.execute("""
        require 'monitor'
        m = Monitor.new
        r = []
        v = m.synchronize { m.synchronize { r << m.mon_owned? }; 7 }
        r << v << m.mon_locked?
        begin
          m.mon_synchronize { raise "boom" }
        rescue => e
          r << e.message << m.mon_locked?
        end
        return r
        """)
        assert self.unwrap(space, w_res) == [True, 7, False, "boom", False]

    def test_mixin(self, space):
        w_res = space.execute("""
        require 'monitor'
        class Box
          include MonitorMixin
          def initialize(x)
            super()
            @x = x
          end
          attr_reader :x
        end
        b = Box.new(3)
        r = [b.x, b.mon_locked?]
        b.synchronize { r << b.mon_owned? }
        r << b.mon_locked?
        o = Object.new.extend(MonitorMixin)
        o.mon_enter
        r << o.mon_locked?
        o.mon_exit
        r << o.mon_locked?
        c = b.new_cond
        r << c.class.name
        return r
        """)
        assert self.unwrap(space, w_res) == [3, False, True, False, True, False, "MonitorMixin::ConditionVariable"]

    def test_cond_wait_timeout(self, space):
        w_res = space.execute("""
        require 'monitor'
        m = Monitor.new
        c = m.new_cond
        m.synchronize do
          m.synchronize do
            c.wait(0.001)
            return [m.mon_owned?, m.mon_locked?]
          end
        end
        """)
        assert self.unwrap(space, w_res) == [True, True]
