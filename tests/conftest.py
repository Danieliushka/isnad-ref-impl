"""Global test configuration — runs before any test module imports."""
import os

# Must be set BEFORE any isnad imports — slowapi reads this at init
os.environ["RATELIMIT_ENABLED"] = "False"
# Set admin API key for all tests that use the main API app
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-global")

TEST_API_KEY = os.environ["ADMIN_API_KEY"]
AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}


def pytest_configure(config):
    """Disable rate limiter after all imports."""
    try:
        from isnad.security import limiter
        limiter.enabled = False
    except ImportError:
        pass
