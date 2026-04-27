import pytest
from django.test import override_settings


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="soroscan.urls_test")
def test_404_returns_json(client):
    response = client.get("/this-route-does-not-exist/")

    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert response.json() == {"detail": "Not found."}
