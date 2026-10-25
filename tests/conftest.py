"""Fixtures for the Eurotherm Smart365 tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from .fake_device import FakeSmart365


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading the integration from custom_components."""
    return


@pytest.fixture
async def device(socket_enabled) -> AsyncGenerator[FakeSmart365]:
    """A running fake panel."""
    fake = FakeSmart365()
    await fake.start()
    yield fake
    await fake.stop()
