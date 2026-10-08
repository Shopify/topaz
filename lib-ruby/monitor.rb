# frozen_string_literal: false
#
# Monitor itself (enter, exit, try_enter, synchronize, mon_check_owner,
# mon_locked?, mon_owned?, wait_for_cond) is implemented in RPython, in
# topaz/objects/mutexobject.py, like MRI's ext/monitor/monitor.c. This file is
# the Ruby half of MRI's lib/monitor.rb: MonitorMixin delegates to a Monitor
# held in @mon_data.
require 'thread'

module MonitorMixin
  class ConditionVariable
    def wait(timeout = nil)
      @monitor.mon_check_owner
      @monitor.wait_for_cond(@cond, timeout)
    end

    def wait_while
      while yield
        wait
      end
    end

    def wait_until
      until yield
        wait
      end
    end

    def signal
      @monitor.mon_check_owner
      @cond.signal
    end

    def broadcast
      @monitor.mon_check_owner
      @cond.broadcast
    end

    private

    def initialize(monitor) # :nodoc:
      @monitor = monitor
      @cond = Thread::ConditionVariable.new
    end
  end

  def self.extend_object(obj) # :nodoc:
    super(obj)
    obj.__send__(:mon_initialize)
  end

  def mon_try_enter
    @mon_data.try_enter
  end
  alias try_mon_enter mon_try_enter

  def mon_enter
    @mon_data.enter
  end

  def mon_exit
    mon_check_owner
    @mon_data.exit
  end

  def mon_locked?
    @mon_data.mon_locked?
  end

  def mon_owned?
    @mon_data.mon_owned?
  end

  def mon_synchronize(&b)
    @mon_data.synchronize(&b)
  end
  alias synchronize mon_synchronize

  def new_cond
    unless defined?(@mon_data)
      mon_initialize
      @mon_initialized_by_new_cond = true
    end
    return ConditionVariable.new(@mon_data)
  end

  private

  def initialize(...)
    super
    mon_initialize
  end

  def mon_initialize
    if defined?(@mon_data)
      if defined?(@mon_initialized_by_new_cond)
        return # already initialized.
      elsif @mon_data_owner_object_id == self.object_id
        raise ThreadError, "already initialized"
      end
    end
    @mon_data = ::Monitor.new
    @mon_data_owner_object_id = self.object_id
  end

  def mon_check_owner
    @mon_data.mon_check_owner
  end
end

class Monitor
  def new_cond
    ::MonitorMixin::ConditionVariable.new(self)
  end

  alias try_mon_enter try_enter
  alias mon_try_enter try_enter
  alias mon_enter enter
  alias mon_exit exit
  alias mon_synchronize synchronize
end
