//! Unit tests for `soroscan_core` event logging (issue #1412).
//!
//! The off-chain indexer identifies records purely by topic signature and then
//! decodes the payload, so these tests assert both halves for the events this
//! contract emits: the exact topic tuple and the exact payload value. They also
//! pin the ledger/timestamp fields the indexer paginates on, and assert that
//! rejected calls publish nothing.
//!
//! The crate is `#![no_std]`, so helpers avoid naming `std` collection types:
//! recorded events are indexed by position instead of being collected.

use super::*;
use soroban_sdk::testutils::{Address as _, Events, Ledger as _};
use soroban_sdk::{Env, TryFromVal, Val};

/// A recorded event as the indexer sees it: contract, topics, data.
type Emitted = (Address, Vec<Val>, Val);

/// Number of events recorded so far.
fn event_count(env: &Env) -> u32 {
    env.events().all().len()
}

/// The `index`-th recorded event, cloned out of the event log.
fn event_at(env: &Env, index: u32) -> Emitted {
    env.events()
        .all()
        .get(index)
        .expect("recorded event should exist")
}

/// Decode topic `index` of `event` as a [`Symbol`].
fn topic_symbol(env: &Env, event: &Emitted, index: u32) -> Symbol {
    let raw = event.1.get(index).expect("topic should exist");
    Symbol::try_from_val(env, &raw).expect("topic should be a Symbol")
}

/// Assert `event` carries exactly `expected_len` topics, starting with the
/// two given symbols. Topic 0 namespaces the event, topic 1 selects the
/// event family, so the indexer dispatches on them.
fn assert_topics(env: &Env, event: &Emitted, expected_len: u32, first: Symbol, second: Symbol) {
    assert_eq!(
        event.1.len(),
        expected_len,
        "unexpected topic count for the event"
    );
    assert_eq!(topic_symbol(env, event, 0), first, "unexpected first topic");
    assert_eq!(
        topic_symbol(env, event, 1),
        second,
        "unexpected second topic"
    );
}

/// Registers the contract, initializes it, and authorizes `indexer`.
fn setup(env: &Env) -> (Address, Address, Address) {
    env.mock_all_auths();
    let contract_id = env.register_contract(None, SoroScanCore);
    let client = SoroScanCoreClient::new(env, &contract_id);
    let admin = Address::generate(env);
    let indexer = Address::generate(env);
    client.init(&admin);
    client.add_indexer(&admin, &indexer);
    (contract_id, admin, indexer)
}

// ---------------------------------------------------------------------------
// Indexer / admin lifecycle events
// ---------------------------------------------------------------------------

#[test]
fn add_indexer_event_topics_and_payload() {
    let env = Env::default();
    env.mock_all_auths();
    let contract_id = env.register_contract(None, SoroScanCore);
    let client = SoroScanCoreClient::new(&env, &contract_id);
    let admin = Address::generate(&env);
    let indexer = Address::generate(&env);

    client.init(&admin);
    assert_eq!(event_count(&env), 0, "init publishes no event");

    client.add_indexer(&admin, &indexer);

    assert_eq!(event_count(&env), 1, "add_indexer publishes one event");
    let event = event_at(&env, 0);
    assert_eq!(event.0, contract_id);
    assert_topics(
        &env,
        &event,
        2,
        symbol_short!("indexer"),
        symbol_short!("add"),
    );
    assert_eq!(
        Address::try_from_val(&env, &event.2).expect("payload is an Address"),
        indexer,
        "payload carries the authorized indexer address"
    );
}

#[test]
fn remove_indexer_event_topics_and_payload() {
    let env = Env::default();
    let (contract_id, admin, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    client.remove_indexer(&admin, &indexer);

    assert_eq!(event_count(&env), 2, "add_indexer + remove_indexer");
    let event = event_at(&env, 1);
    assert_topics(
        &env,
        &event,
        2,
        symbol_short!("indexer"),
        symbol_short!("rem"),
    );
    assert_eq!(
        Address::try_from_val(&env, &event.2).expect("payload is an Address"),
        indexer
    );
}

#[test]
fn pause_indexer_event_topics_and_payload() {
    let env = Env::default();
    let (contract_id, admin, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    client.pause_indexer(&admin, &indexer);

    let event = event_at(&env, 1);
    assert_topics(
        &env,
        &event,
        2,
        symbol_short!("indexer"),
        symbol_short!("pause"),
    );
    assert_eq!(
        Address::try_from_val(&env, &event.2).expect("payload is an Address"),
        indexer
    );
}

#[test]
fn resume_indexer_event_topics_and_payload() {
    let env = Env::default();
    let (contract_id, admin, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    client.pause_indexer(&admin, &indexer);
    client.resume_indexer(&admin, &indexer);

    assert_eq!(event_count(&env), 3, "add + pause + resume");
    let event = event_at(&env, 2);
    assert_topics(
        &env,
        &event,
        2,
        symbol_short!("indexer"),
        symbol_short!("resume"),
    );
    assert_eq!(
        Address::try_from_val(&env, &event.2).expect("payload is an Address"),
        indexer
    );
}

#[test]
fn transfer_admin_event_payload_carries_both_addresses() {
    let env = Env::default();
    let (contract_id, admin, _) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);
    let new_admin = Address::generate(&env);

    client.transfer_admin(&admin, &new_admin);

    assert_eq!(event_count(&env), 2, "add_indexer + transfer_admin");
    let event = event_at(&env, 1);
    assert_topics(
        &env,
        &event,
        2,
        symbol_short!("admin"),
        symbol_short!("xfer"),
    );
    let (from, to) = <(Address, Address)>::try_from_val(&env, &event.2)
        .expect("payload is an (old, new) admin pair");
    assert_eq!(from, admin, "payload carries the previous admin");
    assert_eq!(to, new_admin, "payload carries the new admin");
}

#[test]
fn pause_contract_event_topics_and_payload() {
    let env = Env::default();
    let (contract_id, admin, _) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    client.pause(&admin);

    let event = event_at(&env, 1);
    assert_topics(
        &env,
        &event,
        2,
        symbol_short!("admin"),
        symbol_short!("pause"),
    );
    assert_eq!(
        Address::try_from_val(&env, &event.2).expect("payload is an Address"),
        admin
    );
}

#[test]
fn unpause_contract_event_topics_and_payload() {
    let env = Env::default();
    let (contract_id, admin, _) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    client.pause(&admin);
    client.unpause(&admin);

    assert_eq!(event_count(&env), 3, "add_indexer + pause + unpause");
    let event = event_at(&env, 2);
    assert_topics(
        &env,
        &event,
        2,
        symbol_short!("admin"),
        symbol_short!("unpause"),
    );
    assert_eq!(
        Address::try_from_val(&env, &event.2).expect("payload is an Address"),
        admin
    );
}

#[test]
fn rejected_calls_publish_no_events() {
    let env = Env::default();
    let (contract_id, _, _) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);
    let before = event_count(&env);

    let stranger = Address::generate(&env);
    let target = Address::generate(&env);
    let payload_hash = BytesN::from_array(&env, &[7u8; 32]);

    assert!(client.try_add_indexer(&stranger, &stranger).is_err());
    assert!(client
        .try_record_event(&stranger, &target, &symbol_short!("swap"), &payload_hash)
        .is_err());
    assert!(client.try_pause(&stranger).is_err());
    assert!(client.try_init(&stranger).is_err());

    assert_eq!(
        event_count(&env),
        before,
        "rejected calls must not emit events"
    );
}

// ---------------------------------------------------------------------------
// Standard event emission: record_event
// ---------------------------------------------------------------------------

#[test]
fn record_event_topics_and_event_record_payload() {
    let env = Env::default();
    env.ledger().set_sequence_number(4_242);
    env.ledger().set_timestamp(1_700_000_000);
    let (contract_id, _, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    let target = Address::generate(&env);
    let payload_hash = BytesN::from_array(&env, &[0xAB; 32]);

    client.record_event(&indexer, &target, &symbol_short!("swap"), &payload_hash);

    assert_eq!(event_count(&env), 2, "add_indexer + record_event");
    let event = event_at(&env, 1);
    assert_eq!(event.0, contract_id, "event is attributed to the contract");
    assert_topics(
        &env,
        &event,
        2,
        symbol_short!("soroscan"),
        symbol_short!("swap"),
    );

    let record = EventRecord::try_from_val(&env, &event.2).expect("payload is an EventRecord");
    assert_eq!(record.contract_id, target);
    assert_eq!(record.event_type, symbol_short!("swap"));
    assert_eq!(record.payload_hash, payload_hash);
    // Cursor fields the indexer paginates on.
    assert_eq!(record.ledger, 4_242);
    assert_eq!(record.timestamp, 1_700_000_000);
}

#[test]
fn record_event_payload_matches_stored_record() {
    let env = Env::default();
    let (contract_id, _, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    let target = Address::generate(&env);
    let payload_hash = BytesN::from_array(&env, &[0x11; 32]);
    client.record_event(&indexer, &target, &symbol_short!("mint"), &payload_hash);

    let event = event_at(&env, 1);
    let emitted_record = EventRecord::try_from_val(&env, &event.2).expect("payload is a record");
    let stored = client
        .latest_by_type(&symbol_short!("mint"))
        .expect("record stored");
    assert_eq!(
        emitted_record, stored,
        "emitted payload must match the stored record"
    );
}

// ---------------------------------------------------------------------------
// Custom event emissions: structured (SC-38) and tagged (SC-24)
// ---------------------------------------------------------------------------

#[test]
fn record_structured_event_topics_and_payload() {
    let env = Env::default();
    env.ledger().set_sequence_number(99);
    env.ledger().set_timestamp(555_000);
    let (contract_id, _, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    let target = Address::generate(&env);
    let payload_hash = BytesN::from_array(&env, &[0x22; 32]);
    let correlation_id = BytesN::from_array(&env, &[0x33; 32]);

    client.record_structured_event(
        &indexer,
        &target,
        &symbol_short!("escrow"),
        &payload_hash,
        &1,
        &correlation_id,
    );

    assert_eq!(
        event_count(&env),
        2,
        "add_indexer + record_structured_event"
    );
    let event = event_at(&env, 1);
    assert_eq!(event.0, contract_id);
    assert_topics(
        &env,
        &event,
        3,
        symbol_short!("soroscan"),
        symbol_short!("sc38"),
    );
    assert_eq!(
        topic_symbol(&env, &event, 2),
        symbol_short!("escrow"),
        "third topic carries the event type"
    );

    let record = StructuredEventRecord::try_from_val(&env, &event.2)
        .expect("payload is a StructuredEventRecord");
    assert_eq!(record.contract_id, target);
    assert_eq!(record.event_type, symbol_short!("escrow"));
    assert_eq!(record.payload_hash, payload_hash);
    assert_eq!(record.schema_version, 1);
    assert_eq!(record.correlation_id, correlation_id);
    assert_eq!(record.ledger, 99);
    assert_eq!(record.timestamp, 555_000);
}

#[test]
fn record_structured_event_duplicate_correlation_publishes_one_event() {
    let env = Env::default();
    let (contract_id, _, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    let target = Address::generate(&env);
    let payload_hash = BytesN::from_array(&env, &[0x22; 32]);
    let correlation_id = BytesN::from_array(&env, &[0x33; 32]);

    client.record_structured_event(
        &indexer,
        &target,
        &symbol_short!("escrow"),
        &payload_hash,
        &1,
        &correlation_id,
    );
    let after_first = event_count(&env);

    let duplicate = client.try_record_structured_event(
        &indexer,
        &target,
        &symbol_short!("escrow"),
        &payload_hash,
        &1,
        &correlation_id,
    );
    assert_eq!(duplicate, Err(Ok(ContractError::DuplicateCorrelation)));
    assert_eq!(
        event_count(&env),
        after_first,
        "a duplicate correlation id must not emit a second event"
    );
}

#[test]
fn record_tagged_event_topics_and_payload() {
    let env = Env::default();
    env.ledger().set_sequence_number(7);
    env.ledger().set_timestamp(88);
    let (contract_id, _, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    let target = Address::generate(&env);
    let payload_hash = BytesN::from_array(&env, &[0x44; 32]);
    let mut tags = Vec::new(&env);
    tags.push_back(symbol_short!("hot"));
    tags.push_back(symbol_short!("defi"));

    client.record_tagged_event(
        &indexer,
        &target,
        &symbol_short!("trade"),
        &payload_hash,
        &tags,
    );

    assert_eq!(event_count(&env), 2, "add_indexer + record_tagged_event");
    let event = event_at(&env, 1);
    assert_eq!(event.0, contract_id);
    assert_topics(
        &env,
        &event,
        3,
        symbol_short!("soroscan"),
        symbol_short!("sc24"),
    );
    assert_eq!(
        topic_symbol(&env, &event, 2),
        symbol_short!("trade"),
        "third topic carries the event type"
    );

    let record =
        TaggedEventRecord::try_from_val(&env, &event.2).expect("payload is a TaggedEventRecord");
    assert_eq!(record.contract_id, target);
    assert_eq!(record.event_type, symbol_short!("trade"));
    assert_eq!(record.payload_hash, payload_hash);
    assert_eq!(record.tags.len(), 2, "both producer tags are preserved");
    assert_eq!(record.tags.get(0).unwrap(), symbol_short!("hot"));
    assert_eq!(record.tags.get(1).unwrap(), symbol_short!("defi"));
    assert_eq!(record.ledger, 7);
    assert_eq!(record.timestamp, 88);
}

#[test]
fn paused_indexer_cannot_record_tagged_or_structured_events() {
    let env = Env::default();
    let (contract_id, admin, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);
    client.pause_indexer(&admin, &indexer);

    let target = Address::generate(&env);
    let payload_hash = BytesN::from_array(&env, &[0u8; 32]);
    let mut tags = Vec::new(&env);
    tags.push_back(symbol_short!("hot"));
    let before = event_count(&env);

    assert_eq!(
        client.try_record_tagged_event(
            &indexer,
            &target,
            &symbol_short!("trade"),
            &payload_hash,
            &tags,
        ),
        Err(Ok(ContractError::IndexerPaused))
    );
    assert_eq!(
        client.try_record_structured_event(
            &indexer,
            &target,
            &symbol_short!("escrow"),
            &payload_hash,
            &1,
            &BytesN::from_array(&env, &[1u8; 32]),
        ),
        Err(Ok(ContractError::IndexerPaused))
    );
    assert_eq!(event_count(&env), before);
}

#[test]
fn record_tagged_event_rejects_too_many_tags() {
    let env = Env::default();
    let (contract_id, _, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    let target = Address::generate(&env);
    let payload_hash = BytesN::from_array(&env, &[0u8; 32]);
    let mut tags = Vec::new(&env);
    for _ in 0..=MAX_TAGS {
        tags.push_back(symbol_short!("tag"));
    }
    let before = event_count(&env);

    let result = client.try_record_tagged_event(
        &indexer,
        &target,
        &symbol_short!("trade"),
        &payload_hash,
        &tags,
    );
    assert_eq!(result, Err(Ok(ContractError::TooManyTags)));
    assert_eq!(event_count(&env), before);
}

// ---------------------------------------------------------------------------
// Batch emission
// ---------------------------------------------------------------------------

#[test]
fn record_events_batch_emits_one_event_per_entry_plus_summary() {
    let env = Env::default();
    env.ledger().set_sequence_number(21);
    env.ledger().set_timestamp(22);
    let (contract_id, _, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    let target_a = Address::generate(&env);
    let target_b = Address::generate(&env);
    let mut entries = Vec::new(&env);
    entries.push_back(EventEntry {
        contract_id: target_a.clone(),
        event_type: symbol_short!("swap"),
        payload_hash: BytesN::from_array(&env, &[1u8; 32]),
    });
    entries.push_back(EventEntry {
        contract_id: target_b.clone(),
        event_type: symbol_short!("mint"),
        payload_hash: BytesN::from_array(&env, &[2u8; 32]),
    });

    let count = client.record_events_batch(&indexer, &entries);
    assert_eq!(count, 2);

    // add_indexer + one event per entry + the batch summary.
    assert_eq!(event_count(&env), 4);

    let first_event = event_at(&env, 1);
    assert_topics(
        &env,
        &first_event,
        2,
        symbol_short!("soroscan"),
        symbol_short!("swap"),
    );
    let first = EventRecord::try_from_val(&env, &first_event.2).expect("payload is a record");
    assert_eq!(first.contract_id, target_a);
    assert_eq!(first.ledger, 21);
    assert_eq!(first.timestamp, 22);

    let second_event = event_at(&env, 2);
    assert_topics(
        &env,
        &second_event,
        2,
        symbol_short!("soroscan"),
        symbol_short!("mint"),
    );
    let second = EventRecord::try_from_val(&env, &second_event.2).expect("payload is a record");
    assert_eq!(second.contract_id, target_b);

    let summary = event_at(&env, 3);
    assert_topics(
        &env,
        &summary,
        2,
        symbol_short!("soroscan"),
        symbol_short!("batch"),
    );
    let (summary_indexer, batch_len, running_count) =
        <(Address, u32, u64)>::try_from_val(&env, &summary.2)
            .expect("summary payload is (indexer, batch_len, count)");
    assert_eq!(summary_indexer, indexer);
    assert_eq!(batch_len, 2);
    assert_eq!(running_count, 2);
}

#[test]
fn record_events_batch_rejection_publishes_nothing() {
    let env = Env::default();
    let (contract_id, _, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);
    let before = event_count(&env);

    let empty: Vec<EventEntry> = Vec::new(&env);
    assert_eq!(
        client.try_record_events_batch(&indexer, &empty),
        Err(Ok(ContractError::InvalidBatchSize))
    );
    assert_eq!(event_count(&env), before);
}

// ---------------------------------------------------------------------------
// Cross-event expectations for the off-chain indexer
// ---------------------------------------------------------------------------

#[test]
fn soroscan_events_share_the_namespace_topic_and_name_their_family() {
    let env = Env::default();
    let (contract_id, admin, indexer) = setup(&env);
    let client = SoroScanCoreClient::new(&env, &contract_id);

    let target = Address::generate(&env);
    let payload_hash = BytesN::from_array(&env, &[5u8; 32]);

    client.record_event(&indexer, &target, &symbol_short!("swap"), &payload_hash);
    client.record_structured_event(
        &indexer,
        &target,
        &symbol_short!("escrow"),
        &payload_hash,
        &1,
        &BytesN::from_array(&env, &[6u8; 32]),
    );
    let mut tags = Vec::new(&env);
    tags.push_back(symbol_short!("hot"));
    client.record_tagged_event(
        &indexer,
        &target,
        &symbol_short!("trade"),
        &payload_hash,
        &tags,
    );
    let mut entries = Vec::new(&env);
    entries.push_back(EventEntry {
        contract_id: target.clone(),
        event_type: symbol_short!("swap"),
        payload_hash: payload_hash.clone(),
    });
    client.record_events_batch(&indexer, &entries);
    client.pause_indexer(&admin, &indexer);

    let events = env.events().all();
    let mut soroscan_events = 0u32;
    let mut saw_sc38 = false;
    let mut saw_sc24 = false;
    let mut saw_batch = false;
    let mut saw_record = false;

    for event in events.iter() {
        let first = Symbol::try_from_val(&env, &event.1.get(0).expect("topic 0 should exist"))
            .expect("topic 0 should be a Symbol");
        if first != symbol_short!("soroscan") {
            continue;
        }
        soroscan_events += 1;
        assert_eq!(
            event.0, contract_id,
            "soroscan events are attributed to the contract"
        );
        assert!(
            event.1.len() >= 2,
            "soroscan events carry a namespace and a family topic"
        );

        let family = topic_symbol(&env, &event, 1);
        if family == symbol_short!("sc38") {
            saw_sc38 = true;
        } else if family == symbol_short!("sc24") {
            saw_sc24 = true;
        } else if family == symbol_short!("batch") {
            saw_batch = true;
        } else if family == symbol_short!("swap") {
            saw_record = true;
        } else {
            panic!("unexpected soroscan event family: {family:?}");
        }
    }

    // record_event + structured + tagged + batch entry + batch summary.
    assert_eq!(soroscan_events, 5);
    assert!(saw_record, "record_event emits a (soroscan, type) event");
    assert!(saw_sc38, "structured events are namespaced under sc38");
    assert!(saw_sc24, "tagged events are namespaced under sc24");
    assert!(saw_batch, "batches emit a (soroscan, batch) summary");
}
