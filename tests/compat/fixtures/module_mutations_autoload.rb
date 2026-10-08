$autoload_attempts += 1
raise 'retry' if $autoload_attempts == 1
MutationAutoload::Value = 42
