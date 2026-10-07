# Loaded by Bundler.setup when concurrent-ruby is in the bundle.
#
# concurrent-ruby picks its implementations by engine, and for one it does
# not know it uses a map backend that locks around the map's default
# block, which then deadlocks when that block writes back to the map (as
# ActiveSupport::Notifications' does). topaz runs one thread at a time,
# like CRuby with its GVL, so it gets CRuby's choices.
module Concurrent
  def self.on_cruby?
    true
  end
end
