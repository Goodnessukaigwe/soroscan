"""
WebSocket consumers for real-time event streaming.
"""
import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

from .models import TrackedContract

logger = logging.getLogger(__name__)


class EventConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for streaming contract events in real-time.

    URL: ws://host/ws/events/<contract_id>/
    Optional query param: ?event_type=<type> to filter by event type
    """

    async def connect(self):
        self.contract_id = self.scope["url_route"]["kwargs"]["contract_id"]
        self.event_type = self.scope["query_string"].decode().split("event_type=")[-1] if b"event_type=" in self.scope["query_string"] else None

        try:
            contract = await self.get_contract(self.contract_id)
            if not contract:
                await self.close(code=4004)
                return
        except Exception as e:
            logger.error(f"Error validating contract: {e}")
            await self.close(code=4004)
            return

        self.group_name = f"events_{self.contract_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.info(
            f"WebSocket connected: contract_id={self.contract_id}, event_type={self.event_type}"
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(
                f"WebSocket disconnected: contract_id={self.contract_id}, code={close_code}"
            )

    async def contract_event(self, event):
        """
        Handler for 'contract_event' messages sent to the group.
        """
        event_data = event["data"]

        if self.event_type and event_data.get("event_type") != self.event_type:
            return

        await self.send(text_data=json.dumps(event_data))

    @staticmethod
    async def get_contract(contract_id):
        """
        Validate that the contract exists and is active.
        """
        from channels.db import database_sync_to_async

        @database_sync_to_async
        def _get_contract():
            try:
                return TrackedContract.objects.get(contract_id=contract_id, is_active=True)
            except TrackedContract.DoesNotExist:
                return None

        return await _get_contract()
