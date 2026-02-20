"""
WebSocket URL routing for Django Channels.
"""
from django.urls import path

from .consumers import EventConsumer

websocket_urlpatterns = [
    path("ws/events/<str:contract_id>/", EventConsumer.as_asgi()),
]
