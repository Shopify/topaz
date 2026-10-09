# Run with bin/topaz bench/hash_string_lookup.rb [constant|mutable|mixed].
# Each line is seconds for two million successful, alternating-key lookups.
# Discard the first sample (warmup). "mixed" forces generic object storage.
def lookup(hash, keys, count)
  i = 0
  total = 0
  while i < count
    total += hash[keys[i & 1]]
    i += 1
  end
  total
end

mode = ARGV[0] || 'constant'
raise 'unknown mode' unless ['constant', 'mutable', 'mixed'].include?(mode)
stored = ['first-key', 'second-key']
keys = ['first-key', 'second-key']
if mode == 'mutable'
  stored.each { |key| key << '' }
  keys.each { |key| key << '' }
end
hash = {stored[0] => 1, stored[1] => 2}
hash[:other] = 0 if mode == 'mixed'
7.times do
  start = Time.now
  result = lookup(hash, keys, 2000000)
  elapsed = Time.now - start
  raise 'wrong lookup result' unless result == 3000000
  puts elapsed
end
