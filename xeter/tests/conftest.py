# SPDX-License-Identifier: GPL-3.0-only WITH Commons-Clause-1.0
"""
pytest conftest.py — shared fixtures for Xeter test suite.

Provides mock session for unit tests that do not require a real database.
"""

import os

# Set env var defaults BEFORE any service module is imported during collection.
# Both presenter (deps.py) and diagnosticer (main.py) use os.environ["KEY"]
# hard-fail at module level — these setdefaults prevent KeyError at collection time.
os.environ.setdefault("SECRET_KEY", "test-secret-only")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")

import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_session():
    """Return an AsyncMock that simulates a SQLAlchemy AsyncSession.

    This fixture is for pure unit tests. It provides a session-like object
    whose async methods (execute, add, commit, flush, etc.) are mocked and
    do not touch any real database.
    """
    session = AsyncMock()
    return session
