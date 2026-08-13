local key = KEYS[1]

local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call("HMGET", key, "tokens", "last_refill")

local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = math.max(0, now - last_refill)

tokens = math.min(
    capacity,
    tokens + (elapsed * refill_rate)
)

local allowed = 0

if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end

redis.call(
    "HSET",
    key,
    "tokens",
    tokens,
    "last_refill",
    now
)

redis.call(
    "EXPIRE",
    key,
    math.ceil(capacity / refill_rate) + 60
)

local remaining = math.floor(tokens)

return {
    allowed,
    remaining
}