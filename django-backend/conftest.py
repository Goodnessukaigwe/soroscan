import pytest
import os

# Set Django settings module before any Django imports
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "soroscan.settings_test")

import django
from django.conf import settings

# Configure Django for tests
django.setup()


@pytest.fixture(scope="session", autouse=True)
def configure_celery_for_tests():
    """Configure Celery to run tasks synchronously without Redis broker"""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.CELERY_BROKER_URL = 'memory://'
    settings.CELERY_RESULT_BACKEND = 'cache+memory://'
    
    # Re-configure the Celery app with test settings
    from soroscan.celery import app
    app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        broker_url='memory://',
        result_backend='cache+memory://',
    )


@pytest.fixture(scope="session")
def celery_config():
    return {
        "broker_url": "memory://",
        "result_backend": "cache+memory://",
        "task_always_eager": True,
        "task_eager_propagates": True,
    }


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    pass
