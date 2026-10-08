# Reuse hot call sites before and after changing their ancestor chains.
def check_hot(object, expected)
  15000.times do
    raise "stale lookup" unless object.f == expected
  end
  p object.f
end

class MutationBase
  def f; 0; end
end
module MutationOuter
  def f; super + 1; end
end
module MutationMiddle
  include MutationOuter
end
class MutationUser < MutationBase
  include MutationMiddle
end
object = MutationUser.new
check_hot(object, 1)
module MutationInner
  def f; 10; end
end
MutationOuter.include(MutationInner)
check_hot(object, 11)
module MutationWrap
  def f; super + 100; end
end
MutationOuter.prepend(MutationWrap)
check_hot(object, 111)

module ClonePrepend
  def f; super + 2; end
end
original = MutationBase.new
def original.f; super + 5; end
original.singleton_class.prepend(ClonePrepend)
copy = original.clone
check_hot(copy, 7)
module ClonePrepend
  def f; super + 4; end
end
check_hot(copy, 9)

module VisibilityOriginal
  attr_reader :value
end
visibility_copy = VisibilityOriginal.dup
visibility_copy.send(:private, :value)
p VisibilityOriginal.public_instance_methods(false).include?(:value)
receiver = Object.new
receiver.extend(visibility_copy)
receiver.instance_variable_set(:@value, 42)
p receiver.send(:value)

$autoload_attempts = 0
module MutationAutoload; end
MutationAutoload.autoload(:Value, File.expand_path('fixtures/module_mutations_autoload.rb', File.dirname(__FILE__)))
begin
  MutationAutoload::Value
rescue RuntimeError
end
p MutationAutoload.autoload?(:Value).nil?
p MutationAutoload::Value
p $autoload_attempts
