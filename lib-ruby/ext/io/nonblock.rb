# io/nonblock.so: topaz's IO is always blocking; the flag is remembered.
class IO
  def nonblock?
    @__topaz_nonblock ? true : false
  end

  def nonblock=(value)
    @__topaz_nonblock = value ? true : false
  end

  def nonblock(value = true)
    old = nonblock?
    self.nonblock = value
    yield self
  ensure
    self.nonblock = old
  end
end
