import time
from enum import Enum

from app.core.redis import redis_client


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


FAILURE_THRESHOLD = 3
RECOVERY_TIMEOUT = 30


class CircuitBreaker:
    def __init__(
        self,
        service: str,
        failure_threshold: int = FAILURE_THRESHOLD,
        recovery_timeout: int = RECOVERY_TIMEOUT,
    ):
        self.service = service
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

    @property
    def state_key(self) -> str:
        return f"circuit:{self.service}:state"

    @property
    def failures_key(self) -> str:
        return f"circuit:{self.service}:failures"

    @property
    def opened_at_key(self) -> str:
        return f"circuit:{self.service}:opened_at"

    def get_state(self) -> CircuitState:
        state = redis_client.get(self.state_key)

        if isinstance(state, bytes):
            state = state.decode("utf-8")

        if state == CircuitState.OPEN.value:
            opened_at = redis_client.get(
                self.opened_at_key
            )

            if isinstance(opened_at, bytes):
                opened_at = opened_at.decode("utf-8")

            if opened_at is not None:
                elapsed = time.time() - float(opened_at)

                if elapsed >= self.recovery_timeout:
                    redis_client.set(
                        self.state_key,
                        CircuitState.HALF_OPEN.value,
                        ex=self.recovery_timeout * 2,
                    )

                    return CircuitState.HALF_OPEN

            return CircuitState.OPEN

        if state == CircuitState.HALF_OPEN.value:
            return CircuitState.HALF_OPEN

        return CircuitState.CLOSED

    def record_success(self) -> None:
        redis_client.delete(
            self.failures_key,
            self.opened_at_key,
        )

        redis_client.set(
            self.state_key,
            CircuitState.CLOSED.value,
            ex=self.recovery_timeout * 2,
        )

    def record_failure(self) -> None:
        failures = redis_client.incr(
            self.failures_key
        )

        redis_client.expire(
            self.failures_key,
            self.recovery_timeout * 2,
        )

        if failures >= self.failure_threshold:
            now = str(time.time())

            redis_client.set(
                self.state_key,
                CircuitState.OPEN.value,
                ex=self.recovery_timeout * 2,
            )

            redis_client.set(
                self.opened_at_key,
                now,
                ex=self.recovery_timeout * 2,
            )

    def allow_request(self) -> bool:
        state = self.get_state()

        return state in {
            CircuitState.CLOSED,
            CircuitState.HALF_OPEN,
        }