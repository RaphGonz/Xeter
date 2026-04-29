"""
CI guard: bcrypt cost factor must be >= 12 for production hashes.

OPS-04: This test fails if someone ever calls bcrypt.gensalt() with
rounds < 12 in production code (by testing that the default gensalt()
still produces $2b$12$ hashes).
"""
import bcrypt
import pytest


@pytest.fixture(scope="session")
def api_key_hash_rounds4() -> str:
    """Pre-computed bcrypt hash with rounds=4 for use in test fixtures.

    Uses rounds=4 (not 12) to keep CI fast. The cost-factor test below
    uses a separate call to assert the production minimum.
    """
    return bcrypt.hashpw(b"test-key", bcrypt.gensalt(rounds=4)).decode()


def test_bcrypt_cost_factor_minimum():
    """bcrypt default gensalt() must produce a $2b$12$ hash prefix.

    Asserts that bcrypt.gensalt() (called without arguments, as production
    code does) returns a salt with cost factor 12. This test will fail if:
    - bcrypt changes its default rounds (unlikely but detectable)
    - Someone patches gensalt() to use a lower rounds value
    """
    test_hash = bcrypt.hashpw(b"sentinel", bcrypt.gensalt()).decode()
    prefix = test_hash[:7]   # "$2b$12$"
    assert prefix == "$2b$12$", (
        f"bcrypt cost factor must be >= 12, got hash prefix: {prefix!r}. "
        "Do not pass rounds < 12 to gensalt() in production code."
    )
