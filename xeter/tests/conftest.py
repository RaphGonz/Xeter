"""
pytest conftest.py — shared fixtures for Xeter test suite.

Provides mock session for unit tests that do not require a real database.
"""

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
