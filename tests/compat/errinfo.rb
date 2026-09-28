# $! and Exception#cause.
p((raise "x" rescue $!.message))
p $!
begin
  raise "a"
rescue
  begin
    raise "b"
  rescue
    p $!.message
  end
  p $!.message
end
p $!
def m
  raise ArgumentError, "inner"
rescue => e
  [e.message, $!.message]
end
p m
begin
  begin
    raise "outer"
  ensure
    p $!.message
  end
rescue
end
p $!
begin
  begin
    raise "c"
  rescue => e
    begin; raise "d"; rescue; end
    raise
  end
rescue => e2
  p e2.message
end
begin
  begin
    raise "a"
  rescue
    raise "b"
  end
rescue => e
  p [e.message, e.cause.message, e.cause.cause]
end
begin
  raise ArgumentError, "x", cause: nil
rescue => e
  p e.cause
end
begin
  begin
    raise "a"
  rescue
    raise TypeError, "t", cause: RuntimeError.new("c")
  end
rescue => e
  p e.cause.message
end
begin
  raise IOError, "bt", ["x.rb:1"]
rescue => e
  p e.backtrace
end
begin
  begin
    raise "same"
  rescue => s
    raise s
  end
rescue => e
  p e.cause
end
