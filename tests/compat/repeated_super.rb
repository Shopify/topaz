module RepeatedSuper
  def f
    $super_calls += 1
    return [:cycle] if $super_calls > 5
    [:m] + super
  end
end
module SuperMiddle
  def f; [:middle] + super; end
end
class SuperBase
  def f; [:base]; end
end
class SuperUser < SuperBase
  include SuperMiddle
  include RepeatedSuper
end

def check_super(object, expected)
  15000.times do
    $super_calls = 0
    raise 'wrong super lookup' unless object.f == expected
  end
  p expected
end

object = SuperUser.new
check_super(object, [:m, :middle, :base])
SuperMiddle.include(RepeatedSuper)
check_super(object, [:m, :middle, :m, :base])

module RepeatedSuper
  define_method(:f) do
    $super_calls += 1
    return [:cycle] if $super_calls > 5
    [:block] + proc { super() }.call
  end
end
check_super(object, [:block, :middle, :block, :base])

module RepeatedSuper
  define_method(:f, instance_method(:f))
end
check_super(object, [:block, :middle, :block, :base])
