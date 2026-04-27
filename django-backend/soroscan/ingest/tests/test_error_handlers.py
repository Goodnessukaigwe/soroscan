import pytest
from django.test import Client, override_settings
from django.urls import path

from soroscan.urls import handler404_view, handler500_view


def boom(request):
    raise RuntimeError("deliberate error")


# Minimal urlconf used for the 500 test
urlpatterns = [path("test-500/", boom)]
handler404 = handler404_view
handler500 = handler500_view


@pytest.fixture
def client():
    return Client(raise_request_exception=False)


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_404_returns_json(client):
    response = client.get("/api/this-route-does-not-exist/")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "Not found"
    assert data["status"] == 404
    assert "request_id" in data


@pytest.mark.django_db
@override_settings(DEBUG=False, ROOT_URLCONF=__name__)
def test_500_returns_json(client):
    response = client.get("/test-500/")
    assert response.status_code == 500
    data = response.json()
    assert data["error"] == "Internal server error"
    assert data["status"] == 500
    assert "request_id" in data
