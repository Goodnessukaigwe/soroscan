"""Tests for CDC streaming to Kafka/PubSub/SQS."""
import pytest
from unittest.mock import patch
from django.conf import settings
from soroscan.ingest import streaming
from soroscan.ingest.tasks import process_new_event
from .factories import ContractEventFactory

@pytest.mark.django_db
class TestEventStreaming:
    @patch("soroscan.ingest.tasks.dispatch_webhook.delay")
    @patch("soroscan.ingest.tasks.evaluate_alert_rules.apply_async")
    @patch("soroscan.ingest.streaming.KafkaProducer")
    def test_process_event_streams_to_kafka_when_enabled(self, MockKafkaProducer, MockAlerts, MockWebhooks, contract):
        # Setup mock producer
        mock_producer_instance = MockKafkaProducer.return_value

        # Configure settings for Kafka
        streaming_settings = {
            "enabled": True,
            "backend": "kafka",
            "kafka": {
                "bootstrap_servers": ["localhost:9092"],
                "topic": "soroscan.events",
                "schema_registry_url": "",
            },
        }
        
        with patch.object(settings, "EVENT_STREAMING", streaming_settings):
            # Force re-initialization of producer singleton for test
            from soroscan.ingest import streaming
            streaming._producer_instance = None
            
            event = ContractEventFactory(contract=contract, event_type="swap", ledger=1000, event_index=0)
            event_data = {
                "contract_id": contract.contract_id,
                "event_type": "swap",
                "payload": event.payload,
                "ledger": event.ledger,
                "event_index": event.event_index,
                "tx_hash": event.tx_hash,
            }
            
            process_new_event.apply(args=[event_data])
            
            # Verify producer was initialized and publish was called
            MockKafkaProducer.assert_called_once()
            mock_producer_instance.publish.assert_called_once_with(
                contract.contract_id, event_data
            )

    @patch("soroscan.ingest.streaming.requests.post")
    def test_kafka_schema_registry_registration(self, mock_post):
        mock_post.return_value.raise_for_status.return_value = None
        client = streaming.SchemaRegistryClient("http://schema-registry:8081")
        client.register_schema(streaming.CDC_SCHEMA_SUBJECT, streaming.CDC_EVENT_SCHEMA_V1)
        mock_post.assert_called_once()

    @patch("soroscan.ingest.tasks.dispatch_webhook.delay")
    @patch("soroscan.ingest.tasks.evaluate_alert_rules.apply_async")
    @patch("soroscan.ingest.streaming.PubSubProducer")
    def test_process_event_streams_to_pubsub_when_enabled(self, MockPubSubProducer, MockAlerts, MockWebhooks, contract):
        # Setup mock producer
        mock_producer_instance = MockPubSubProducer.return_value

        # Configure settings for Pub/Sub
        streaming_settings = {
            "enabled": True,
            "backend": "pubsub",
            "pubsub": {
                "project_id": "test-project",
                "topic": "soroscan.events",
            },
        }
        
        with patch.object(settings, "EVENT_STREAMING", streaming_settings):
            # Force re-initialization of producer singleton for test
            from soroscan.ingest import streaming
            streaming._producer_instance = None
            
            event = ContractEventFactory(
                contract=contract, event_type="swap", ledger=2000, event_index=0
            )
            event_data = {
                "contract_id": contract.contract_id,
                "event_type": "swap",
                "payload": event.payload,
                "ledger": event.ledger,
                "event_index": event.event_index,
                "tx_hash": event.tx_hash,
            }
            
            process_new_event.apply(args=[event_data])
            
            # Verify producer was initialized and publish was called
            MockPubSubProducer.assert_called_once()
            mock_producer_instance.publish.assert_called_once_with(
                contract.contract_id, event_data
            )

    @patch("soroscan.ingest.tasks.dispatch_webhook.delay")
    @patch("soroscan.ingest.tasks.evaluate_alert_rules.apply_async")
    def test_process_event_no_streaming_when_disabled(self, MockAlerts, MockWebhooks, contract):
        # Configure settings to disabled
        streaming_settings = {"enabled": False}
        
        with patch.object(settings, "EVENT_STREAMING", streaming_settings):
            # Force re-initialization
            from soroscan.ingest import streaming
            streaming._producer_instance = None
            
            with patch("soroscan.ingest.streaming.KafkaProducer") as MockKafka:
                ContractEventFactory(contract=contract)
                event_data = {"contract_id": contract.contract_id}
                process_new_event.apply(args=[event_data])
                
                MockKafka.assert_not_called()

    @patch("soroscan.ingest.tasks.dispatch_webhook.delay")
    @patch("soroscan.ingest.tasks.evaluate_alert_rules.apply_async")
    @patch("soroscan.ingest.streaming.SQSProducer")
    def test_process_event_streams_to_sqs_when_enabled(self, MockSQSProducer, MockAlerts, MockWebhooks, contract):
        mock_producer_instance = MockSQSProducer.return_value

        streaming_settings = {
            "enabled": True,
            "backend": "sqs",
            "sqs": {"queue_url": "https://sqs.us-east-1.amazonaws.com/123456789012/soroscan-events"},
        }

        with patch.object(settings, "EVENT_STREAMING", streaming_settings):
            from soroscan.ingest import streaming

            streaming._producer_instance = None
            event = ContractEventFactory(contract=contract, event_type="swap", ledger=2001, event_index=0)
            event_data = {
                "contract_id": contract.contract_id,
                "event_type": event.event_type,
                "payload": event.payload,
                "ledger": event.ledger,
                "event_index": event.event_index,
                "tx_hash": event.tx_hash,
            }
            process_new_event.apply(args=[event_data])

            MockSQSProducer.assert_called_once()
            mock_producer_instance.publish.assert_called_once_with(contract.contract_id, event_data)

    @patch("soroscan.ingest.tasks.dispatch_webhook.delay")
    @patch("soroscan.ingest.tasks.evaluate_alert_rules.apply_async")
    @patch("soroscan.ingest.streaming.KafkaProducer")
    def test_streaming_failure_does_not_block_process_new_event(self, MockKafkaProducer, MockAlerts, MockWebhooks, contract):
        mock_producer_instance = MockKafkaProducer.return_value
        mock_producer_instance.publish.side_effect = Exception("Streaming failed")

        streaming_settings = {
            "enabled": True,
            "backend": "kafka",
            "kafka": {
                "bootstrap_servers": ["localhost:9092"],
                "topic": "soroscan.events",
                "schema_registry_url": "",
            },
        }
        
        with patch.object(settings, "EVENT_STREAMING", streaming_settings):
            from soroscan.ingest import streaming
            streaming._producer_instance = None

            event = ContractEventFactory(
                contract=contract, event_type="swap", ledger=3000, event_index=0
            )
            event_data = {
                "contract_id": contract.contract_id,
                "event_type": "swap",
                "ledger": event.ledger,
                "event_index": event.event_index,
            }
            
            # Should NOT raise exception
            process_new_event.apply(args=[event_data])
            
            mock_producer_instance.publish.assert_called_once()
