import pytest
from .factories import UserFactory, TrackedContractFactory

@pytest.fixture
def user():
    return UserFactory()

@pytest.fixture
def contract(user):
    return TrackedContractFactory(owner=user)
