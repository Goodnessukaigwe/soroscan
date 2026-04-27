import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.urls import reverse
from unittest.mock import patch

from soroscan.ingest.admin import WebhookDeliveryLogAdmin
from soroscan.ingest.models import WebhookDeliveryLog
from soroscan.ingest.tests.factories import WebhookSubscriptionFactory, ContractEventFactory



@pytest.mark.django_db
class TestWebhookRetryAction:
    def setup_method(self):
        self.site = AdminSite()
        self.admin = WebhookDeliveryLogAdmin(WebhookDeliveryLog, self.site)
        self.rf = RequestFactory()

    def _setup_request(self, request):
        request.user = type('User', (), {
            'is_staff': True, 
            'is_active': True, 
            'is_authenticated': True, 
            'has_perm': lambda x, y=None: True
        })()
        # Mock _messages to avoid MessageFailure
        request._messages = []
        return request

    def test_retry_action_confirmation_page(self):
        """Test that the action returns a confirmation page initially."""
        sub = WebhookSubscriptionFactory()
        event = ContractEventFactory(contract=sub.contract)
        log = WebhookDeliveryLog.objects.create(
            subscription=sub,
            event=event,
            success=False,
            status_code=500
        )
        
        queryset = WebhookDeliveryLog.objects.filter(pk=log.pk)
        request = self.rf.post(reverse('admin:ingest_webhookdeliverylog_changelist'), {
            'action': 'retry_webhook_delivery',
            '_selected_action': [str(log.pk)]
        })
        self._setup_request(request)
        
        response = self.admin.retry_webhook_delivery(request, queryset)
        
        assert response.status_code == 200
        assert 'admin/ingest/webhookdeliverylog/webhook_retry_confirmation.html' in response.template_name
        assert queryset.count() == 1

    @patch('soroscan.ingest.admin.dispatch_webhook.delay')
    @patch('django.contrib.messages.add_message')
    def test_retry_action_execution(self, mock_add_message, mock_dispatch):
        """Test that the action triggers the Celery task when confirmed."""
        sub = WebhookSubscriptionFactory()
        event = ContractEventFactory(contract=sub.contract)
        log = WebhookDeliveryLog.objects.create(
            subscription=sub,
            event=event,
            success=False,
            status_code=500
        )
        
        queryset = WebhookDeliveryLog.objects.filter(pk=log.pk)
        # Simulate the POST from the confirmation page
        request = self.rf.post(reverse('admin:ingest_webhookdeliverylog_changelist'), {
            'action': 'retry_webhook_delivery',
            '_selected_action': [str(log.pk)],
            'post': 'yes'
        })
        self._setup_request(request)
        
        response = self.admin.retry_webhook_delivery(request, queryset)
        
        assert response is None  # Admin actions return None to redirect back to changelist
        mock_dispatch.assert_called_once_with(sub.id, event.id)
        assert mock_add_message.called

    @patch('soroscan.ingest.admin.dispatch_webhook.delay')
    @patch('django.contrib.messages.add_message')
    def test_retry_multiple_logs(self, mock_add_message, mock_dispatch):
        """Test retrying multiple logs at once."""
        sub = WebhookSubscriptionFactory()
        event1 = ContractEventFactory(contract=sub.contract)
        event2 = ContractEventFactory(contract=sub.contract)
        log1 = WebhookDeliveryLog.objects.create(subscription=sub, event=event1, success=False)
        log2 = WebhookDeliveryLog.objects.create(subscription=sub, event=event2, success=False)
        
        queryset = WebhookDeliveryLog.objects.filter(pk__in=[log1.pk, log2.pk])
        request = self.rf.post(reverse('admin:ingest_webhookdeliverylog_changelist'), {
            'action': 'retry_webhook_delivery',
            '_selected_action': [str(log1.pk), str(log2.pk)],
            'post': 'yes'
        })
        self._setup_request(request)
        
        self.admin.retry_webhook_delivery(request, queryset)
        
        assert mock_dispatch.call_count == 2
        # Check if it was called for each event
        calls = [c[0] for c in mock_dispatch.call_args_list]
        assert (sub.id, event1.id) in calls
        assert (sub.id, event2.id) in calls
        assert mock_add_message.called
