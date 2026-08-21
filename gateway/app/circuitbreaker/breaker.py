import time
from enum import Enum

from redis.exceptions import RedisError

from app.core.redis import redis_client


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    def __init__(
        self,
        service: str,
        failure_threshold: int = 3,
        recovery_timeout: int = 30,
    ):
        self.service = service
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

    @property
    def state_key(self):
        return f"circuit:{self.service}:state"

    @property
    def failures_key(self):
        return f"circuit:{self.service}:failures"

    @property
    def opened_at_key(self):
        return f"circuit:{self.service}:opened_at"

    def get_state(self) -> CircuitState:
        try:
            state = redis_client.get(self.state_key)

            if state is None:
                return CircuitState.CLOSED

            if isinstance(state, bytes):
                state = state.decode()

            if state == CircuitState.OPEN.value:
                opened_at = redis_client.get(
                    self.opened_at_key
                )

                if opened_at is not None:
                    if isinstance(opened_at, bytes):
                        opened_at = opened_at.decode()

                    elapsed = (
                        time.time() - float(opened_at)
                    )

                    if elapsed >= self.recovery_timeout:
                        redis_client.set(
                            self.state_key,
                            CircuitState.HALF_OPEN.value,
                        )

                        return CircuitState.HALF_OPEN

            return CircuitState(state)

        except RedisError:
            return CircuitState.CLOSED

    def record_success(self):
        try:
            redis_client.set(
                self.state_key,
                CircuitState.CLOSED.value,
            )

            redis_client.delete(
                self.failures_key,
                self.opened_at_key,
            )

        except RedisError:
            pass

    def record_failure(self):
        try:
            failures = redis_client.incr(
                self.failures_key
            )

            redis_client.expire(
                self.failures_key,
                self.recovery_timeout * 2,
            )

            if failures >= self.failure_threshold:
                redis_client.set(
                    self.state_key,
                    CircuitState.OPEN.value,
                )

                redis_client.set(
                    self.opened_at_key,
                    str(time.time()),
                )

                redis_client.expire(
                    self.state_key,
                    self.recovery_timeout * 2,
                )

        except RedisError:
            pass

    def allow_request(self) -> bool:
        state = self.get_state()

        return state in {
            CircuitState.CLOSED,
            CircuitState.HALF_OPEN,
        }