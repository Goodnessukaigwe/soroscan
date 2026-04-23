# CDC Streaming Integrations

SoroScan can publish every newly indexed event to downstream systems in real-time.

## Stream payload

- Kafka/PubSub/SQS messages use schema subject `soroscan.events-value`
- current schema version: `1`
- default topic name: `soroscan.events`

Event envelope fields:

- `schema_version`
- `emitted_at`
- `contract_id`
- `event_type`
- `ledger`
- `event_index`
- `tx_hash`
- `payload` (JSON string)

## Enable CDC publishing

Set these environment variables in `django-backend/.env`:

```env
EVENT_STREAMING_ENABLED=true
EVENT_STREAMING_BACKEND=kafka
KAFKA_BOOTSTRAP_SERVERS=broker-1:9092,broker-2:9092
KAFKA_TOPIC=soroscan.events
KAFKA_SCHEMA_REGISTRY_URL=http://schema-registry:8081
```

## Snowflake via Kafka connector

1. Configure SoroScan with Kafka backend (`EVENT_STREAMING_BACKEND=kafka`).
2. Create Snowflake table and Kafka connector:

```sql
CREATE TABLE SOROSCAN_EVENTS_RAW (
  RECORD VARIANT
);
```

Use Snowflake Kafka Connector targeting topic `soroscan.events` and load each message body into `RECORD`.

## BigQuery / Redshift patterns

- **BigQuery**: connect Kafka -> BigQuery using Confluent managed sink, mapping to a JSON/STRUCT schema.
- **Redshift**: connect Kafka -> S3 sink -> Redshift COPY pipeline, or use managed Kafka Connect Redshift sink.

## AWS SQS option

Set:

```env
EVENT_STREAMING_ENABLED=true
EVENT_STREAMING_BACKEND=sqs
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/soroscan-events
```

SoroScan publishes one message per event. FIFO queues are supported by automatically setting `MessageGroupId`.
