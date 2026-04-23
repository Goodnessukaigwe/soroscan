"""CDC event streaming producers for Kafka, Pub/Sub, and AWS queues."""
import json
import logging
from datetime import datetime, timezone
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def _get_metrics():
    from soroscan.ingest import metrics
    return metrics

class BaseProducer:
    def publish(self, contract_id: str, event_data: dict[str, Any]):
        raise NotImplementedError


CDC_SCHEMA_SUBJECT = "soroscan.events-value"
CDC_SCHEMA_VERSION = 1
CDC_EVENT_SCHEMA_V1 = {
    "type": "record",
    "name": "SoroScanEvent",
    "namespace": "io.soroscan.cdc",
    "fields": [
        {"name": "schema_version", "type": "int"},
        {"name": "emitted_at", "type": "string"},
        {"name": "contract_id", "type": "string"},
        {"name": "event_type", "type": ["null", "string"], "default": None},
        {"name": "ledger", "type": ["null", "long"], "default": None},
        {"name": "event_index", "type": ["null", "int"], "default": None},
        {"name": "tx_hash", "type": ["null", "string"], "default": None},
        {"name": "payload", "type": ["null", "string"], "default": None},
    ],
}


def build_cdc_envelope(event_data: dict[str, Any]) -> dict[str, Any]:
    payload = event_data.get("payload")
    payload_text = json.dumps(payload, separators=(",", ":"), sort_keys=True) if payload else None
    return {
        "schema_version": CDC_SCHEMA_VERSION,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "contract_id": event_data.get("contract_id"),
        "event_type": event_data.get("event_type"),
        "ledger": event_data.get("ledger"),
        "event_index": event_data.get("event_index"),
        "tx_hash": event_data.get("tx_hash"),
        "payload": payload_text,
    }


class SchemaRegistryClient:
    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def register_schema(self, subject: str, schema_dict: dict[str, Any]) -> None:
        schema_text = json.dumps(schema_dict, separators=(",", ":"))
        response = requests.post(
            f"{self.url}/subjects/{subject}/versions",
            json={"schemaType": "AVRO", "schema": schema_text},
            timeout=5,
        )
        response.raise_for_status()


class KafkaProducer(BaseProducer):
    def __init__(self, bootstrap_servers: list[str], topic: str, schema_registry_url: str | None = None):
        try:
            from kafka import KafkaProducer as KP
            self.producer = KP(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                # Async by default, non-blocking
                acks=1,
                retries=3,
            )
            self.topic = topic
            logger.info("Kafka producer initialized with servers: %s", bootstrap_servers)
            if schema_registry_url:
                try:
                    SchemaRegistryClient(schema_registry_url).register_schema(
                        CDC_SCHEMA_SUBJECT,
                        CDC_EVENT_SCHEMA_V1,
                    )
                except Exception:
                    logger.exception("Failed to register CDC schema in schema registry")
        except Exception:
            logger.exception("Failed to initialize Kafka producer")
            self.producer = None

    def publish(self, contract_id: str, event_data: dict[str, Any]):
        if not self.producer:
            return

        try:
            message = build_cdc_envelope(event_data)
            key = (event_data.get("tx_hash") or contract_id or "").encode("utf-8")
            self.producer.send(self.topic, message, key=key).add_callback(
                self._on_success
            ).add_errback(
                self._on_error
            )
        except Exception:
            logger.exception("Failed to send event to Kafka topic %s", self.topic)
            _get_metrics().event_streaming_total.labels(status="failure", backend="kafka").inc()

    def _on_success(self, record_metadata):
        _get_metrics().event_streaming_total.labels(status="success", backend="kafka").inc()

    def _on_error(self, exc):
        logger.warning("Kafka publish failed: %s", exc)
        _get_metrics().event_streaming_total.labels(status="failure", backend="kafka").inc()

class PubSubProducer(BaseProducer):
    def __init__(self, project_id: str, topic: str):
        try:
            from google.cloud import pubsub_v1
            self.publisher = pubsub_v1.PublisherClient()
            self.project_id = project_id
            self.topic = topic
            logger.info("Pub/Sub producer initialized for project: %s", project_id)
        except Exception:
            logger.exception("Failed to initialize Pub/Sub producer")
            self.publisher = None

    def publish(self, contract_id: str, event_data: dict[str, Any]):
        if not self.publisher:
            return

        topic_path = self.publisher.topic_path(self.project_id, self.topic)
        
        try:
            data = json.dumps(build_cdc_envelope(event_data)).encode("utf-8")
            # publish() is asynchronous and returns a Future
            future = self.publisher.publish(topic_path, data)
            future.add_done_callback(self._on_complete)
        except Exception:
            logger.exception("Failed to publish event to Pub/Sub topic %s", topic_path)
            _get_metrics().event_streaming_total.labels(status="failure", backend="pubsub").inc()

    def _on_complete(self, future):
        try:
            future.result()
            _get_metrics().event_streaming_total.labels(status="success", backend="pubsub").inc()
        except Exception as exc:
            logger.warning("Pub/Sub publish failed: %s", exc)
            _get_metrics().event_streaming_total.labels(status="failure", backend="pubsub").inc()


class SQSProducer(BaseProducer):
    def __init__(self, queue_url: str):
        self.queue_url = queue_url
        try:
            import boto3

            self.client = boto3.client("sqs")
        except Exception:
            logger.exception("Failed to initialize SQS producer")
            self.client = None

    def publish(self, contract_id: str, event_data: dict[str, Any]):
        if not self.client:
            return
        try:
            params = {
                "QueueUrl": self.queue_url,
                "MessageBody": json.dumps(build_cdc_envelope(event_data)),
            }
            if self.queue_url.endswith(".fifo"):
                params["MessageGroupId"] = (event_data.get("tx_hash") or contract_id or "soroscan")[:128]
            self.client.send_message(**params)
            _get_metrics().event_streaming_total.labels(status="success", backend="sqs").inc()
        except Exception:
            logger.exception("Failed to publish event to SQS queue %s", self.queue_url)
            _get_metrics().event_streaming_total.labels(status="failure", backend="sqs").inc()

# Singleton-ish access to the configured producer
_producer_instance = None

def get_producer():
    global _producer_instance
    if _producer_instance is not None:
        return _producer_instance

    config = settings.EVENT_STREAMING
    if not config.get("enabled"):
        return None

    backend = config.get("backend")
    if backend == "kafka":
        kafka_cfg = config.get("kafka", {})
        _producer_instance = KafkaProducer(
            bootstrap_servers=kafka_cfg.get("bootstrap_servers", ["localhost:9092"]),
            topic=kafka_cfg.get("topic", "soroscan.events"),
            schema_registry_url=kafka_cfg.get("schema_registry_url"),
        )
    elif backend == "pubsub":
        ps_cfg = config.get("pubsub", {})
        _producer_instance = PubSubProducer(
            project_id=ps_cfg.get("project_id", ""),
            topic=ps_cfg.get("topic", "soroscan.events"),
        )
    elif backend == "sqs":
        sqs_cfg = config.get("sqs", {})
        queue_url = sqs_cfg.get("queue_url", "")
        if not queue_url:
            logger.warning("SQS backend enabled but no queue_url configured")
            return None
        _producer_instance = SQSProducer(queue_url=queue_url)
    else:
        logger.warning("Unknown streaming backend: %s", backend)
        return None

    return _producer_instance
