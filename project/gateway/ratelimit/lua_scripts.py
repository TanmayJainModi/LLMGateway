"""
lua_scripts.py

Atomic Lua scripts for Redis-based token bucket rate limiting.

These scripts execute atomically inside Redis, preventing
race conditions across multiple concurrent gateway instances.
"""

# =============================================================
# TOKEN_BUCKET_LUA
# =============================================================
#
# Atomic token bucket: read → refill → check → subtract.
#
# KEYS[1]: bucket key (e.g. ratelimit:tma:17:rpm)
# ARGV[1]: capacity (max tokens in bucket)
# ARGV[2]: refill_rate (tokens added per second)
# ARGV[3]: cost (tokens to consume for this request)
# ARGV[4]: current_timestamp (seconds, float-safe)
#
# Returns: {allowed (0|1), remaining, retry_after}
# =============================================================

TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local now = tonumber(ARGV[4])
local min_reserve_pct = tonumber(ARGV[5] or "0.0")

local data = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if not tokens then
    tokens = capacity
    last_refill = now
else
    local elapsed = math.max(0, now - last_refill)
    tokens = math.min(capacity, tokens + (elapsed * refill_rate))
    last_refill = now
end

local min_reserve_tokens = capacity * min_reserve_pct
local remaining_after_cost = tokens - cost

if remaining_after_cost >= min_reserve_tokens then
    tokens = remaining_after_cost
    redis.call("HMSET", key, "tokens", tokens, "last_refill", last_refill)
    redis.call("EXPIRE", key, 3600)
    return {1, math.floor(tokens), 0}
else
    local needed = cost - tokens + min_reserve_tokens
    local retry_after = math.ceil(math.max(1, needed / refill_rate))
    redis.call("HMSET", key, "tokens", tokens, "last_refill", last_refill)
    redis.call("EXPIRE", key, 3600)
    return {0, math.floor(tokens), retry_after}
end
"""

# =============================================================
# REFUND_LUA
# =============================================================
#
# Atomically refund unused tokens back to the TPM bucket
# after the actual provider usage is known.
#
# KEYS[1]: bucket key (e.g. ratelimit:tma:17:tpm)
# ARGV[1]: refund_amount (tokens to return)
# ARGV[2]: capacity (max tokens — never exceed this)
#
# Returns: {new_remaining}
# =============================================================

REFUND_LUA = """
local key = KEYS[1]
local refund = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])

local data = redis.call("HMGET", key, "tokens")
local tokens = tonumber(data[1])

if not tokens then
    tokens = capacity
else
    tokens = math.min(capacity, tokens + refund)
end

redis.call("HSET", key, "tokens", tokens)
return math.floor(tokens)
"""

# =============================================================
# DAILY_COUNTER_LUA
# =============================================================
#
# Increment a daily request counter.
# The key auto-expires after 24 hours.
#
# KEYS[1]: counter key (e.g. ratelimit:tma:17:rpd:2026-08-05)
# ARGV[1]: daily_limit
#
# Returns: {allowed (0|1), current_count, retry_after}
# =============================================================

DAILY_COUNTER_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])

local current = tonumber(redis.call("GET", key) or "0")

if current < limit then
    redis.call("INCR", key)
    if current == 0 then
        redis.call("EXPIRE", key, 86400)
    end
    return {1, current + 1, 0}
else
    local ttl = tonumber(redis.call("TTL", key))
    if ttl < 0 then
        ttl = 86400
    end
    return {0, current, ttl}
end
"""

# =============================================================
# CLAIM_QUEUE_ITEM_LUA
# =============================================================
#
# Atomically check if a request_id exists in queue metadata hash,
# and delete it if present so only one worker claims execution.
#
# KEYS[1]: queue_meta key (e.g. ratelimit:queue_meta:17)
# ARGV[1]: request_id
#
# Returns: 1 if claimed successfully, 0 if already claimed/deleted.
# =============================================================

CLAIM_QUEUE_ITEM_LUA = """
local key = KEYS[1]
local req_id = ARGV[1]

if redis.call("HEXISTS", key, req_id) == 1 then
    redis.call("HDEL", key, req_id)
    return 1
else
    return 0
end
"""

