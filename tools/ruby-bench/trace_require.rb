# Load before run.rb to print each feature as it is required.
module Kernel
  alias __traced_require require
  def require(path)
    $stderr.puts "require #{path}" if ENV["TRACE_REQUIRE"]
    __traced_require(path)
  end
  private :require
end
