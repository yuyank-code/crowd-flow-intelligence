import pytest

from app.core import security


@pytest.fixture(autouse=True)
def reset_rate_limiters():
    """Rate limiters are process-wide; keep tests independent of each other."""
    for lim in (security.operator_limiter, security.geo_limiter, security.parse_limiter, security.live_limiter):
        lim.reset()
    yield
