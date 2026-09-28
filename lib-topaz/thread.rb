class ThreadError < StandardError
end

class ClosedQueueError < StopIteration
end

# Topaz runs a single thread. Thread.new records its block, and the block runs
# when the thread is joined or its value is asked for. A thread that is never
# joined (a timer, a connection reaper) never runs.
class Thread
  class << self
    def abort_on_exception=(value)
      @abort_on_exception = !!value
    end

    def abort_on_exception
      @abort_on_exception ||= false
    end

    def report_on_exception=(value)
      @report_on_exception = !!value
    end

    def report_on_exception
      @report_on_exception.nil? ? true : @report_on_exception
    end

    def new(*args, &block)
      raise ThreadError, "must be called with a block" unless block
      thread = allocate
      thread.__send__(:__topaz_setup, args, block)
      thread
    end
    alias start new
    alias fork new

    def main
      current
    end

    def list
      [current]
    end

    def pass
      nil
    end

    def stop
      nil
    end

    def handle_interrupt(hash)
      yield
    end

    def pending_interrupt?(error = nil)
      false
    end

    def exit
      current.exit
    end
    alias kill exit
  end

  def abort_on_exception=(value)
    @abort_on_exception = !!value
  end

  def abort_on_exception
    @abort_on_exception ||= (Thread.abort_on_exception || false)
  end

  def report_on_exception=(value)
    @report_on_exception = !!value
  end

  def report_on_exception
    @report_on_exception.nil? ? Thread.report_on_exception : @report_on_exception
  end

  def name
    @name
  end

  def name=(name)
    @name = name.nil? ? nil : name.to_s
  end

  def priority
    @priority || 0
  end

  def priority=(value)
    @priority = value
  end

  def join(limit = nil)
    __topaz_run
    Kernel.raise @exception if @exception
    self
  end

  def value
    join
    @value
  end

  def status
    return "run" if equal?(Thread.main)
    return "run" if @block
    @exception ? nil : false
  end

  def alive?
    equal?(Thread.main) || !@block.nil?
  end

  def stop?
    !alive?
  end

  def kill
    if equal?(Thread.main)
      raise SystemExit
    end
    @block = nil
    self
  end
  alias exit kill
  alias terminate kill

  def wakeup
    self
  end

  def run
    __topaz_run
    self
  end

  def raise(*args)
    if equal?(Thread.current)
      Kernel.raise(*args)
    end
    @block = nil
    nil
  end

  def backtrace(*args)
    equal?(Thread.current) ? caller(*args) : nil
  end

  def native_thread_id
    Process.pid
  end

  def group
    nil
  end

  def fetch(key, *default)
    key = key.to_sym
    return self[key] if key?(key)
    return yield(key) if block_given?
    return default[0] unless default.empty?
    Kernel.raise KeyError, "key not found: #{key.inspect}"
  end

  def thread_variable_get(key)
    (@thread_variables ||= {})[key.to_sym]
  end

  def thread_variable_set(key, value)
    (@thread_variables ||= {})[key.to_sym] = value
  end

  def thread_variable?(key)
    (@thread_variables ||= {}).key?(key.to_sym)
  end

  def thread_variables
    (@thread_variables ||= {}).keys
  end

  def inspect
    "#<Thread:0x#{object_id.to_s(16)} #{status || "dead"}>"
  end
  alias to_s inspect

  private

  def __topaz_setup(args, block)
    @args = args
    @block = block
  end

  def __topaz_run
    block = @block
    return unless block
    @block = nil
    begin
      @value = block.call(*@args)
    rescue Exception => e
      @exception = e
    end
  end

  class Mutex
    def initialize
      @locked = false
    end

    def lock
      Kernel.raise ThreadError, "deadlock; recursive locking" if @locked
      @locked = true
      self
    end

    def try_lock
      return false if @locked
      @locked = true
    end

    def unlock
      Kernel.raise ThreadError, "Attempt to unlock a mutex which is not locked" unless @locked
      @locked = false
      self
    end

    def locked?
      @locked
    end

    def owned?
      @locked
    end

    def synchronize
      lock
      begin
        yield
      ensure
        unlock
      end
    end

    def sleep(timeout = nil)
      unlock
      begin
        timeout ? Kernel.sleep(timeout) : Kernel.raise(ThreadError, "No live threads left. Deadlock?")
      ensure
        lock
      end
    end
  end

  class ConditionVariable
    def wait(mutex, timeout = nil)
      # Nothing else can signal: without a timeout this would wait forever.
      Kernel.raise ThreadError, "No live threads left. Deadlock?" if timeout.nil?
      mutex.sleep(timeout)
      self
    end

    def signal
      self
    end

    def broadcast
      self
    end
  end

  class Queue
    def initialize(items = nil)
      @que = items ? items.to_a.dup : []
      @closed = false
    end

    def push(obj)
      Kernel.raise ClosedQueueError, "queue closed" if @closed
      @que.push(obj)
      self
    end
    alias << push
    alias enq push

    def pop(non_block = false, timeout: nil)
      if @que.empty?
        Kernel.raise ThreadError, "queue empty" if non_block
        return nil if @closed || timeout
        Kernel.raise ThreadError, "No live threads left. Deadlock?"
      end
      @que.shift
    end
    alias shift pop
    alias deq pop

    def close
      @closed = true
      self
    end

    def closed?
      @closed
    end

    def empty?
      @que.empty?
    end

    def clear
      @que.clear
      self
    end

    def length
      @que.length
    end
    alias size length

    def num_waiting
      0
    end

    def freeze
      Kernel.raise TypeError, "cannot freeze #{self}"
    end
  end

  class SizedQueue < Queue
    attr_reader :max

    def initialize(max)
      super()
      self.max = max
    end

    def max=(max)
      max = Topaz.convert_type(max, Integer, :to_int)
      Kernel.raise ArgumentError, "queue size must be positive" if max <= 0
      @max = max
    end

    def push(obj, non_block = false, timeout: nil)
      if length >= @max
        Kernel.raise ThreadError, "queue full" if non_block
        return nil if timeout
        Kernel.raise ThreadError, "No live threads left. Deadlock?"
      end
      super(obj)
    end
    alias << push
    alias enq push
  end
end

Mutex = Thread::Mutex
ConditionVariable = Thread::ConditionVariable
Queue = Thread::Queue
SizedQueue = Thread::SizedQueue

module ObjectSpace
  # Topaz's weak maps hold their entries strongly.
  class WeakMap
    include Enumerable

    def initialize
      @map = {}.compare_by_identity
    end

    def [](key)
      @map[key]
    end

    def []=(key, value)
      @map[key] = value
    end

    def key?(key)
      @map.key?(key)
    end
    alias include? key?
    alias member? key?

    def delete(key)
      return @map.delete(key) if @map.key?(key)
      block_given? ? yield(key) : nil
    end

    def each(&block)
      @map.each(&block)
      self
    end
    alias each_pair each

    def each_key(&block)
      @map.each_key(&block)
      self
    end

    def each_value(&block)
      @map.each_value(&block)
      self
    end

    def keys
      @map.keys
    end

    def values
      @map.values
    end

    def size
      @map.size
    end
    alias length size

    def inspect
      "#<ObjectSpace::WeakMap #{@map.map { |k, v| "#{k.inspect} => #{v.inspect}" }.join(", ")}>"
    end
  end

  class WeakKeyMap
    def initialize
      @map = {}
    end

    def [](key)
      @map[key]
    end

    def []=(key, value)
      @map[key] = value
    end

    def key?(key)
      @map.key?(key)
    end

    def getkey(key)
      @map.each_key { |k| return k if k.eql?(key) }
      nil
    end

    def delete(key)
      return @map.delete(key) if @map.key?(key)
      block_given? ? yield(key) : nil
    end

    def clear
      @map.clear
      self
    end

    def inspect
      "#<ObjectSpace::WeakKeyMap size=#{@map.size}>"
    end
  end
end
