# A minimal GC module. RPython's GC is not controllable from Ruby, so these
# mostly report that nothing happened.
module GC
  def self.start(full_mark: true, immediate_sweep: true)
    nil
  end

  def self.count
    0
  end

  def self.stat(key = nil)
    stats = {count: 0, heap_live_slots: 0, total_allocated_objects: 0,
             total_freed_objects: 0, major_gc_count: 0, minor_gc_count: 0}
    key ? stats[key] : stats
  end

  def self.enable
    false
  end

  def self.disable
    false
  end

  def self.stress
    false
  end

  def self.stress=(value)
    value
  end

  def self.compact
    nil
  end

  def garbage_collect(full_mark: true, immediate_sweep: true)
    nil
  end
end
