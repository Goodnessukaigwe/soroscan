#![no_std]
use soroban_sdk::{
    contract, contracterror, contractimpl, contracttype, symbol_short, Address, BytesN, Env, Map,
    Symbol, Vec,
};

// Storage keys
const ADMIN_KEY: Symbol = symbol_short!("admin");
const INDEXERS_KEY: Symbol = symbol_short!("idxrs");
const COUNTER_KEY: Symbol = symbol_short!("count");
const CONTRACT_STATS_KEY: Symbol = symbol_short!("cstats");
const CONTRACT_EVENT_TYPES_KEY: Symbol = symbol_short!("etypes");

/// Represents a recorded event from an indexed contract.
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EventRecord {
    /// The contract that emitted the original event.
    pub contract_id: Address,
    /// The type/category of the event.
    pub event_type: Symbol,
    /// SHA-256 hash of the event payload for verification.
    pub payload_hash: BytesN<32>,
    /// Ledger sequence number when recorded.
    pub ledger: u32,
    /// Unix timestamp when recorded.
    pub timestamp: u64,
}

/// Indexer registration status (SC-10).
#[contracttype]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum IndexerStatus {
    /// Indexer is active and can record events.
    Active = 0,
    /// Indexer is paused; it remains registered but cannot record events.
    Paused = 1,
}

/// A single event entry used in batch recording (SC-29).
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EventEntry {
    /// The contract that emitted the original event.
    pub contract_id: Address,
    /// The type/category of the event.
    pub event_type: Symbol,
    /// SHA-256 hash of the event payload for verification.
    pub payload_hash: BytesN<32>,
}

/// Per-contract event statistics (SC-17).
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ContractStats {
    /// Total number of events recorded for this contract.
    pub event_count: u64,
}

/// A versioned, correlation-tracked event record (SC-38), extended with a
/// revocation flag so erroneous submissions can be marked invalid (SC-42).
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct StructuredEventRecord {
    /// The contract that emitted the original event.
    pub contract_id: Address,
    /// The type/category of the event.
    pub event_type: Symbol,
    /// SHA-256 hash of the event payload for verification.
    pub payload_hash: BytesN<32>,
    /// Schema version of the payload (must be >= 1).
    pub schema_version: u32,
    /// Caller-supplied 32-byte id used to deduplicate retries.
    pub correlation_id: BytesN<32>,
    /// Ledger sequence number when recorded.
    pub ledger: u32,
    /// Unix timestamp when recorded.
    pub timestamp: u64,
    /// Whether the event has been revoked (SC-42).
    pub revoked: bool,
}

/// Storage keys for structured event records (SC-38 / SC-42).
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DataKey {
    /// Looks up a structured event record by its correlation ID.
    StructuredByCorrelation(BytesN<32>),
    /// Tracks the most recently recorded structured event for an event type.
    LatestStructuredByType(Symbol),
}

/// Contract errors with explicit error codes.
#[contracterror]
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum ContractError {
    /// Caller is not authorized to perform this action.
    Unauthorized = 1,
    /// The specified indexer address is not registered.
    IndexerNotFound = 2,
    /// Contract has already been initialized.
    AlreadyInitialized = 3,
    /// Contract has not been initialized.
    NotInitialized = 4,
    /// Batch is empty or exceeds the maximum allowed size.
    InvalidBatchSize = 5,
    /// The indexer is currently paused and cannot record events (SC-10).
    IndexerPaused = 6,
    /// Schema version must be greater than zero (SC-38).
    InvalidSchemaVersion = 7,
    /// A structured event with this correlation ID has already been recorded (SC-38).
    DuplicateCorrelation = 8,
    /// No structured event exists for the given correlation ID (SC-42).
    StructuredEventNotFound = 9,
    /// The structured event has already been revoked (SC-42).
    AlreadyRevoked = 10,
}

#[contract]
pub struct SoroScanCore;

#[contractimpl]
impl SoroScanCore {
    /// Initialize the contract with an admin address.
    /// Can only be called once.
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `admin` - The admin address that can manage indexers
    pub fn init(env: Env, admin: Address) -> Result<(), ContractError> {
        if env.storage().instance().has(&ADMIN_KEY) {
            return Err(ContractError::AlreadyInitialized);
        }

        env.storage().instance().set(&ADMIN_KEY, &admin);
        env.storage()
            .instance()
            .set(&INDEXERS_KEY, &Map::<Address, IndexerStatus>::new(&env));
        env.storage().instance().set(&COUNTER_KEY, &0u64);

        Ok(())
    }

    /// Add an authorized indexer address.
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `admin` - The admin address (must match stored admin)
    /// * `indexer` - The indexer address to authorize
    pub fn add_indexer(env: Env, admin: Address, indexer: Address) -> Result<(), ContractError> {
        admin.require_auth();

        let stored_admin: Address = env
            .storage()
            .instance()
            .get(&ADMIN_KEY)
            .ok_or(ContractError::NotInitialized)?;

        if admin != stored_admin {
            return Err(ContractError::Unauthorized);
        }

        let mut indexers: Map<Address, IndexerStatus> = env
            .storage()
            .instance()
            .get(&INDEXERS_KEY)
            .ok_or(ContractError::NotInitialized)?;

        indexers.set(indexer.clone(), IndexerStatus::Active);
        env.storage().instance().set(&INDEXERS_KEY, &indexers);

        // Emit event for indexer addition
        env.events()
            .publish((symbol_short!("indexer"), symbol_short!("add")), indexer);

        Ok(())
    }

    /// Remove an authorized indexer address.
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `admin` - The admin address (must match stored admin)
    /// * `indexer` - The indexer address to remove
    pub fn remove_indexer(env: Env, admin: Address, indexer: Address) -> Result<(), ContractError> {
        admin.require_auth();

        let stored_admin: Address = env
            .storage()
            .instance()
            .get(&ADMIN_KEY)
            .ok_or(ContractError::NotInitialized)?;

        if admin != stored_admin {
            return Err(ContractError::Unauthorized);
        }

        let mut indexers: Map<Address, IndexerStatus> = env
            .storage()
            .instance()
            .get(&INDEXERS_KEY)
            .ok_or(ContractError::NotInitialized)?;

        indexers.remove(indexer.clone());
        env.storage().instance().set(&INDEXERS_KEY, &indexers);

        // Emit event for indexer removal
        env.events()
            .publish((symbol_short!("indexer"), symbol_short!("rem")), indexer);

        Ok(())
    }

    /// Record an event from an indexed contract.
    /// Only authorized indexers can call this function.
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `indexer` - The indexer address (must be authorized)
    /// * `contract_id` - The contract that emitted the original event
    /// * `event_type` - The type/category of the event
    /// * `payload_hash` - SHA-256 hash of the event payload
    ///
    /// # Returns
    /// The new total event count
    pub fn record_event(
        env: Env,
        indexer: Address,
        contract_id: Address,
        event_type: Symbol,
        payload_hash: BytesN<32>,
    ) -> Result<u64, ContractError> {
        indexer.require_auth();

        let indexers: Map<Address, IndexerStatus> = env
            .storage()
            .instance()
            .get(&INDEXERS_KEY)
            .ok_or(ContractError::NotInitialized)?;

        match indexers.get(indexer) {
            Some(IndexerStatus::Active) => {}
            Some(IndexerStatus::Paused) => return Err(ContractError::IndexerPaused),
            None => return Err(ContractError::IndexerNotFound),
        }

        let ledger = env.ledger().sequence();
        let timestamp = env.ledger().timestamp();

        let record = EventRecord {
            contract_id: contract_id.clone(),
            event_type: event_type.clone(),
            payload_hash,
            ledger,
            timestamp,
        };

        // Increment counter with overflow protection
        let mut count: u64 = env.storage().instance().get(&COUNTER_KEY).unwrap_or(0);
        count = count.saturating_add(1);
        env.storage().instance().set(&COUNTER_KEY, &count);

        // Store latest event by type
        env.storage().instance().set(&event_type, &record);

        // Update per-contract event count (SC-17)
        let mut contract_stats: Map<Address, ContractStats> = env
            .storage()
            .instance()
            .get(&CONTRACT_STATS_KEY)
            .unwrap_or(Map::new(&env));
        let current_stats = contract_stats.get(contract_id.clone()).unwrap_or(ContractStats { event_count: 0 });
        contract_stats.set(
            contract_id.clone(),
            ContractStats {
                event_count: current_stats.event_count.saturating_add(1),
            },
        );
        env.storage().instance().set(&CONTRACT_STATS_KEY, &contract_stats);

        // Track unique event types per contract (SC-17)
        let mut contract_types: Map<Address, Vec<Symbol>> = env
            .storage()
            .instance()
            .get(&CONTRACT_EVENT_TYPES_KEY)
            .unwrap_or(Map::new(&env));
        let mut types = contract_types.get(contract_id.clone()).unwrap_or(Vec::new(&env));
        if !types.contains(&event_type) {
            types.push_back(event_type.clone());
            contract_types.set(contract_id.clone(), types);
            env.storage().instance().set(&CONTRACT_EVENT_TYPES_KEY, &contract_types);
        }

        // Publish the event for off-chain indexers
        env.events()
            .publish((symbol_short!("soroscan"), event_type), record);

        Ok(count)
    }

    /// Record an SC-38 structured event.
    ///
    /// `correlation_id` makes producer retries safe: a duplicate is rejected
    /// before incrementing the counter or publishing a second event.
    pub fn record_structured_event(
        env: Env,
        indexer: Address,
        contract_id: Address,
        event_type: Symbol,
        payload_hash: BytesN<32>,
        schema_version: u32,
        correlation_id: BytesN<32>,
    ) -> Result<u64, ContractError> {
        indexer.require_auth();

        if schema_version == 0 {
            return Err(ContractError::InvalidSchemaVersion);
        }

        let indexers: Map<Address, IndexerStatus> = env
            .storage()
            .instance()
            .get(&INDEXERS_KEY)
            .ok_or(ContractError::NotInitialized)?;

        match indexers.get(indexer) {
            Some(IndexerStatus::Active) => {}
            Some(IndexerStatus::Paused) => return Err(ContractError::IndexerPaused),
            None => return Err(ContractError::IndexerNotFound),
        }

        let correlation_key = DataKey::StructuredByCorrelation(correlation_id.clone());
        if env.storage().instance().has(&correlation_key) {
            return Err(ContractError::DuplicateCorrelation);
        }

        let record = StructuredEventRecord {
            contract_id,
            event_type: event_type.clone(),
            payload_hash,
            schema_version,
            correlation_id,
            ledger: env.ledger().sequence(),
            timestamp: env.ledger().timestamp(),
            revoked: false,
        };

        let count = env
            .storage()
            .instance()
            .get::<Symbol, u64>(&COUNTER_KEY)
            .unwrap_or(0)
            .saturating_add(1);
        env.storage().instance().set(&COUNTER_KEY, &count);
        env.storage().instance().set(&correlation_key, &record);
        env.storage().instance().set(
            &DataKey::LatestStructuredByType(event_type.clone()),
            &record,
        );
        env.events().publish(
            (symbol_short!("soroscan"), symbol_short!("sc38"), event_type),
            record,
        );

        Ok(count)
    }

    /// Get a structured event by its SC-38 correlation ID.
    pub fn structured_by_correlation(
        env: Env,
        correlation_id: BytesN<32>,
    ) -> Option<StructuredEventRecord> {
        env.storage()
            .instance()
            .get(&DataKey::StructuredByCorrelation(correlation_id))
    }

    /// Revoke a previously recorded SC-38 structured event (SC-42).
    ///
    /// Revocation lets an authorized indexer flag a submission it recorded in
    /// error (e.g. bad payload hash) as invalid without deleting the audit
    /// trail. Revocation is permanent and rejects a second attempt so callers
    /// get an explicit signal rather than a silent no-op.
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `indexer` - The indexer address (must be authorized and active)
    /// * `correlation_id` - The correlation ID of the structured event to revoke
    pub fn revoke_structured_event(
        env: Env,
        indexer: Address,
        correlation_id: BytesN<32>,
    ) -> Result<(), ContractError> {
        indexer.require_auth();

        let indexers: Map<Address, IndexerStatus> = env
            .storage()
            .instance()
            .get(&INDEXERS_KEY)
            .ok_or(ContractError::NotInitialized)?;

        match indexers.get(indexer.clone()) {
            Some(IndexerStatus::Active) => {}
            Some(IndexerStatus::Paused) => return Err(ContractError::IndexerPaused),
            None => return Err(ContractError::IndexerNotFound),
        }

        let key = DataKey::StructuredByCorrelation(correlation_id.clone());
        let mut record: StructuredEventRecord = env
            .storage()
            .instance()
            .get(&key)
            .ok_or(ContractError::StructuredEventNotFound)?;

        if record.revoked {
            return Err(ContractError::AlreadyRevoked);
        }

        record.revoked = true;
        env.storage().instance().set(&key, &record);

        // Keep the "latest by type" projection in sync when it points at the
        // record being revoked.
        let latest_key = DataKey::LatestStructuredByType(record.event_type.clone());
        if let Some(latest) = env
            .storage()
            .instance()
            .get::<DataKey, StructuredEventRecord>(&latest_key)
        {
            if latest.correlation_id == record.correlation_id {
                env.storage().instance().set(&latest_key, &record);
            }
        }

        env.events().publish(
            (
                symbol_short!("soroscan"),
                symbol_short!("sc42"),
                symbol_short!("revoke"),
            ),
            (indexer, record),
        );

        Ok(())
    }

    /// Check whether an SC-38 structured event has been revoked (SC-42).
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `correlation_id` - The correlation ID of the structured event to check
    ///
    /// # Returns
    /// `true` if the event exists and has been revoked, `false` if it exists
    /// and is still valid, or `ContractError::StructuredEventNotFound` if no
    /// event with that correlation ID has been recorded.
    pub fn is_structured_event_revoked(
        env: Env,
        correlation_id: BytesN<32>,
    ) -> Result<bool, ContractError> {
        let record: StructuredEventRecord = env
            .storage()
            .instance()
            .get(&DataKey::StructuredByCorrelation(correlation_id))
            .ok_or(ContractError::StructuredEventNotFound)?;
        Ok(record.revoked)
    }

    /// Get the latest event record for a specific event type.
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `event_type` - The event type to query
    ///
    /// # Returns
    /// The latest EventRecord for the type, or None if not found
    pub fn latest_by_type(env: Env, event_type: Symbol) -> Option<EventRecord> {
        env.storage().instance().get(&event_type)
    }

    /// Get the total number of events recorded.
    ///
    /// # Arguments
    /// * `env` - The contract environment
    ///
    /// # Returns
    /// The total event count
    pub fn total_events(env: Env) -> u64 {
        env.storage().instance().get(&COUNTER_KEY).unwrap_or(0)
    }

    /// Get the total event count for a specific contract (SC-17).
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `contract_id` - The contract address to query
    ///
    /// # Returns
    /// The total event count for the contract
    pub fn contract_event_count(env: Env, contract_id: Address) -> u64 {
        let contract_stats: Option<Map<Address, ContractStats>> =
            env.storage().instance().get(&CONTRACT_STATS_KEY);
        match contract_stats {
            Some(stats) => stats.get(contract_id).map(|s| s.event_count).unwrap_or(0),
            None => 0,
        }
    }

    /// Get the unique event types recorded for a specific contract (SC-17).
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `contract_id` - The contract address to query
    ///
    /// # Returns
    /// A vector of event type Symbols for the contract
    pub fn contract_event_types(env: Env, contract_id: Address) -> Vec<Symbol> {
        let contract_types: Option<Map<Address, Vec<Symbol>>> =
            env.storage().instance().get(&CONTRACT_EVENT_TYPES_KEY);
        match contract_types {
            Some(types) => types.get(contract_id).unwrap_or(Vec::new(&env)),
            None => Vec::new(&env),
        }
    }

    /// Check if an address is an authorized indexer.
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `indexer` - The address to check
    ///
    /// # Returns
    /// true if the address is registered and active, false otherwise
    pub fn is_indexer(env: Env, indexer: Address) -> bool {
        let indexers: Option<Map<Address, IndexerStatus>> =
            env.storage().instance().get(&INDEXERS_KEY);
        match indexers {
            Some(map) => map.get(indexer) == Some(IndexerStatus::Active),
            None => false,
        }
    }

    /// Record multiple events in a single transaction (SC-29).
    /// Only authorized indexers can call this function.
    /// Maximum batch size is 25 events.
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `indexer` - The indexer address (must be authorized)
    /// * `events` - Vec of EventEntry structs to record
    ///
    /// # Returns
    /// The new total event count after recording all events
    pub fn record_events_batch(
        env: Env,
        indexer: Address,
        events: Vec<EventEntry>,
    ) -> Result<u64, ContractError> {
        indexer.require_auth();

        let batch_len = events.len();
        if batch_len == 0 || batch_len > 25 {
            return Err(ContractError::InvalidBatchSize);
        }

        let indexers: Map<Address, IndexerStatus> = env
            .storage()
            .instance()
            .get(&INDEXERS_KEY)
            .ok_or(ContractError::NotInitialized)?;

        match indexers.get(indexer.clone()) {
            Some(IndexerStatus::Active) => {}
            Some(IndexerStatus::Paused) => return Err(ContractError::IndexerPaused),
            None => return Err(ContractError::IndexerNotFound),
        }

        let ledger = env.ledger().sequence();
        let timestamp = env.ledger().timestamp();
        let mut count: u64 = env.storage().instance().get(&COUNTER_KEY).unwrap_or(0);

        let mut contract_stats: Map<Address, ContractStats> = env
            .storage()
            .instance()
            .get(&CONTRACT_STATS_KEY)
            .unwrap_or(Map::new(&env));
        let mut contract_types: Map<Address, Vec<Symbol>> = env
            .storage()
            .instance()
            .get(&CONTRACT_EVENT_TYPES_KEY)
            .unwrap_or(Map::new(&env));

        for entry in events.iter() {
            let record = EventRecord {
                contract_id: entry.contract_id.clone(),
                event_type: entry.event_type.clone(),
                payload_hash: entry.payload_hash.clone(),
                ledger,
                timestamp,
            };

            count = count.saturating_add(1);
            env.storage().instance().set(&entry.event_type, &record);

            // Update per-contract event count (SC-17)
            let current_stats = contract_stats.get(entry.contract_id.clone()).unwrap_or(ContractStats { event_count: 0 });
            contract_stats.set(
                entry.contract_id.clone(),
                ContractStats {
                    event_count: current_stats.event_count.saturating_add(1),
                },
            );

            // Track unique event types per contract (SC-17)
            let mut types = contract_types.get(entry.contract_id.clone()).unwrap_or(Vec::new(&env));
            if !types.contains(&entry.event_type) {
                types.push_back(entry.event_type.clone());
                contract_types.set(entry.contract_id.clone(), types);
            }

            env.events().publish(
                (symbol_short!("soroscan"), entry.event_type.clone()),
                record,
            );
        }

        env.storage().instance().set(&COUNTER_KEY, &count);
        env.storage().instance().set(&CONTRACT_STATS_KEY, &contract_stats);
        env.storage().instance().set(&CONTRACT_EVENT_TYPES_KEY, &contract_types);

        // Emit a single batch summary event
        env.events().publish(
            (symbol_short!("soroscan"), symbol_short!("batch")),
            (indexer, batch_len, count),
        );

        Ok(count)
    }

    /// Pause an indexer, preventing it from recording events (SC-10).
    /// The indexer remains registered and can be resumed.
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `admin` - The admin address (must match stored admin)
    /// * `indexer` - The indexer address to pause
    pub fn pause_indexer(env: Env, admin: Address, indexer: Address) -> Result<(), ContractError> {
        admin.require_auth();

        let stored_admin: Address = env
            .storage()
            .instance()
            .get(&ADMIN_KEY)
            .ok_or(ContractError::NotInitialized)?;

        if admin != stored_admin {
            return Err(ContractError::Unauthorized);
        }

        let mut indexers: Map<Address, IndexerStatus> = env
            .storage()
            .instance()
            .get(&INDEXERS_KEY)
            .ok_or(ContractError::NotInitialized)?;

        if !indexers.contains_key(indexer.clone()) {
            return Err(ContractError::IndexerNotFound);
        }

        indexers.set(indexer.clone(), IndexerStatus::Paused);
        env.storage().instance().set(&INDEXERS_KEY, &indexers);

        env.events()
            .publish((symbol_short!("indexer"), symbol_short!("pause")), indexer);

        Ok(())
    }

    /// Resume a paused indexer, allowing it to record events again (SC-10).
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `admin` - The admin address (must match stored admin)
    /// * `indexer` - The indexer address to resume
    pub fn resume_indexer(
        env: Env,
        admin: Address,
        indexer: Address,
    ) -> Result<(), ContractError> {
        admin.require_auth();

        let stored_admin: Address = env
            .storage()
            .instance()
            .get(&ADMIN_KEY)
            .ok_or(ContractError::NotInitialized)?;

        if admin != stored_admin {
            return Err(ContractError::Unauthorized);
        }

        let mut indexers: Map<Address, IndexerStatus> = env
            .storage()
            .instance()
            .get(&INDEXERS_KEY)
            .ok_or(ContractError::NotInitialized)?;

        if !indexers.contains_key(indexer.clone()) {
            return Err(ContractError::IndexerNotFound);
        }

        indexers.set(indexer.clone(), IndexerStatus::Active);
        env.storage().instance().set(&INDEXERS_KEY, &indexers);

        env.events()
            .publish((symbol_short!("indexer"), symbol_short!("resume")), indexer);

        Ok(())
    }

    /// Get the status of a specific indexer (SC-10).
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `indexer` - The indexer address to query
    ///
    /// # Returns
    /// The IndexerStatus if registered, or None if not found
    pub fn get_indexer_status(env: Env, indexer: Address) -> Option<IndexerStatus> {
        let indexers: Option<Map<Address, IndexerStatus>> =
            env.storage().instance().get(&INDEXERS_KEY);
        indexers.and_then(|map| map.get(indexer))
    }

    /// Transfer admin rights to a new address (SC-29).
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `admin` - Current admin address
    /// * `new_admin` - New admin address
    pub fn transfer_admin(
        env: Env,
        admin: Address,
        new_admin: Address,
    ) -> Result<(), ContractError> {
        admin.require_auth();

        let stored_admin: Address = env
            .storage()
            .instance()
            .get(&ADMIN_KEY)
            .ok_or(ContractError::NotInitialized)?;

        if admin != stored_admin {
            return Err(ContractError::Unauthorized);
        }

        env.storage().instance().set(&ADMIN_KEY, &new_admin);

        env.events().publish(
            (symbol_short!("admin"), symbol_short!("xfer")),
            (stored_admin, new_admin),
        );

        Ok(())
    }

    /// Get the admin address.
    ///
    /// # Arguments
    /// * `env` - The contract environment
    ///
    /// # Returns
    /// The admin address, or None if not initialized
    pub fn get_admin(env: Env) -> Option<Address> {
        env.storage().instance().get(&ADMIN_KEY)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use soroban_sdk::testutils::{Address as _, Events};
    use soroban_sdk::Env;

    fn setup_contract(env: &Env) -> (SoroScanCoreClient<'_>, Address, Address) {
        let contract_id = env.register_contract(None, SoroScanCore);
        let client = SoroScanCoreClient::new(env, &contract_id);
        let admin = Address::generate(env);
        let indexer = Address::generate(env);
        client.init(&admin);
        (client, admin, indexer)
    }

    #[test]
    fn test_initialize() {
        let env = Env::default();
        let contract_id = env.register_contract(None, SoroScanCore);
        let client = SoroScanCoreClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        client.init(&admin);

        assert_eq!(client.get_admin(), Some(admin.clone()));
        assert_eq!(client.total_events(), 0);
        assert!(!client.is_indexer(&admin));
    }

    #[test]
    fn test_add_indexer_as_admin() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);

        assert!(!client.is_indexer(&indexer));

        client.add_indexer(&admin, &indexer);

        assert!(client.is_indexer(&indexer));

        let events = env.events().all();
        assert_eq!(events.len(), 1);
    }

    #[test]
    fn test_add_indexer_as_non_admin() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let non_admin = Address::generate(&env);

        let result = client.try_add_indexer(&non_admin, &indexer);
        assert_eq!(result, Err(Ok(ContractError::Unauthorized)));
        assert!(!client.is_indexer(&indexer));

        // Admin can still add the indexer after the failed attempt.
        client.add_indexer(&admin, &indexer);
        assert!(client.is_indexer(&indexer));
    }

    #[test]
    fn test_record_event_whitelisted() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target_contract = Address::generate(&env);

        client.add_indexer(&admin, &indexer);

        let event_type = symbol_short!("swap");
        let payload_hash = BytesN::from_array(&env, &[0u8; 32]);

        let count = client.record_event(&indexer, &target_contract, &event_type, &payload_hash);
        assert_eq!(count, 1);
        assert_eq!(client.total_events(), 1);

        let latest = client
            .latest_by_type(&event_type)
            .expect("event should be stored");
        assert_eq!(latest.event_type, event_type);
        assert_eq!(latest.contract_id, target_contract);
        assert_eq!(latest.payload_hash, payload_hash);

        // record_event publishes a soroscan event in addition to indexer add events.
        let events = env.events().all();
        assert!(events.len() >= 2);
    }

    #[test]
    fn test_record_event_not_whitelisted() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, _admin, _indexer) = setup_contract(&env);
        let rogue = Address::generate(&env);
        let target = Address::generate(&env);

        let event_type = symbol_short!("swap");
        let payload_hash = BytesN::from_array(&env, &[0u8; 32]);

        let result = client.try_record_event(&rogue, &target, &event_type, &payload_hash);
        assert_eq!(result, Err(Ok(ContractError::IndexerNotFound)));
        assert_eq!(client.total_events(), 0);
        assert!(client.latest_by_type(&event_type).is_none());
    }

    #[test]
    fn test_remove_indexer() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);

        client.add_indexer(&admin, &indexer);
        assert!(client.is_indexer(&indexer));

        client.remove_indexer(&admin, &indexer);
        assert!(!client.is_indexer(&indexer));
    }

    #[test]
    fn test_record_events_batch() {
        let env = Env::default();
        env.mock_all_auths();

        let contract_id = env.register_contract(None, SoroScanCore);
        let client = SoroScanCoreClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        let indexer = Address::generate(&env);
        let target1 = Address::generate(&env);
        let target2 = Address::generate(&env);

        client.init(&admin);
        client.add_indexer(&admin, &indexer);

        let mut entries = Vec::new(&env);
        entries.push_back(EventEntry {
            contract_id: target1,
            event_type: symbol_short!("swap"),
            payload_hash: BytesN::from_array(&env, &[1u8; 32]),
        });
        entries.push_back(EventEntry {
            contract_id: target2,
            event_type: symbol_short!("transfer"),
            payload_hash: BytesN::from_array(&env, &[2u8; 32]),
        });

        let count = client.record_events_batch(&indexer, &entries);
        assert_eq!(count, 2);
        assert_eq!(client.total_events(), 2);

        let swap = client.latest_by_type(&symbol_short!("swap"));
        assert!(swap.is_some());
        let transfer = client.latest_by_type(&symbol_short!("transfer"));
        assert!(transfer.is_some());
    }

    #[test]
    fn test_record_events_batch_empty() {
        let env = Env::default();
        env.mock_all_auths();

        let contract_id = env.register_contract(None, SoroScanCore);
        let client = SoroScanCoreClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        let indexer = Address::generate(&env);

        client.init(&admin);
        client.add_indexer(&admin, &indexer);

        let empty: Vec<EventEntry> = Vec::new(&env);
        let result = client.try_record_events_batch(&indexer, &empty);
        assert_eq!(result, Err(Ok(ContractError::InvalidBatchSize)));
    }

    #[test]
    fn test_record_events_batch_too_large() {
        let env = Env::default();
        env.mock_all_auths();

        let contract_id = env.register_contract(None, SoroScanCore);
        let client = SoroScanCoreClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        let indexer = Address::generate(&env);

        client.init(&admin);
        client.add_indexer(&admin, &indexer);

        let mut entries = Vec::new(&env);
        for _ in 0..26 {
            entries.push_back(EventEntry {
                contract_id: Address::generate(&env),
                event_type: symbol_short!("ev"),
                payload_hash: BytesN::from_array(&env, &[0u8; 32]),
            });
        }
        let result = client.try_record_events_batch(&indexer, &entries);
        assert_eq!(result, Err(Ok(ContractError::InvalidBatchSize)));
    }

    #[test]
    fn test_record_events_batch_unauthorized_indexer() {
        let env = Env::default();
        env.mock_all_auths();

        let contract_id = env.register_contract(None, SoroScanCore);
        let client = SoroScanCoreClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        let rogue = Address::generate(&env);

        client.init(&admin);

        let mut entries = Vec::new(&env);
        entries.push_back(EventEntry {
            contract_id: Address::generate(&env),
            event_type: symbol_short!("swap"),
            payload_hash: BytesN::from_array(&env, &[0u8; 32]),
        });

        let result = client.try_record_events_batch(&rogue, &entries);
        assert_eq!(result, Err(Ok(ContractError::IndexerNotFound)));
    }

    #[test]
    fn test_transfer_admin() {
        let env = Env::default();
        env.mock_all_auths();

        let contract_id = env.register_contract(None, SoroScanCore);
        let client = SoroScanCoreClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        let new_admin = Address::generate(&env);

        client.init(&admin);
        assert_eq!(client.get_admin(), Some(admin.clone()));

        client.transfer_admin(&admin, &new_admin);
        assert_eq!(client.get_admin(), Some(new_admin.clone()));
    }

    #[test]
    fn test_transfer_admin_unauthorized() {
        let env = Env::default();
        env.mock_all_auths();

        let contract_id = env.register_contract(None, SoroScanCore);
        let client = SoroScanCoreClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        let non_admin = Address::generate(&env);
        let new_admin = Address::generate(&env);

        client.init(&admin);

        let result = client.try_transfer_admin(&non_admin, &new_admin);
        assert_eq!(result, Err(Ok(ContractError::Unauthorized)));
    }

    #[test]
    fn test_double_initialize() {
        let env = Env::default();
        let contract_id = env.register_contract(None, SoroScanCore);
        let client = SoroScanCoreClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        client.init(&admin);

        let result = client.try_init(&admin);
        assert_eq!(result, Err(Ok(ContractError::AlreadyInitialized)));
    }

    #[test]
    fn test_contract_event_count() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);

        client.add_indexer(&admin, &indexer);

        // Initially zero for any contract
        assert_eq!(client.contract_event_count(&target), 0);

        // Record an event and check count
        client.record_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
        );
        assert_eq!(client.contract_event_count(&target), 1);

        // Record another event for the same contract
        client.record_event(
            &indexer,
            &target,
            &symbol_short!("transfer"),
            &BytesN::from_array(&env, &[1u8; 32]),
        );
        assert_eq!(client.contract_event_count(&target), 2);

        // Other contract is unaffected
        let other = Address::generate(&env);
        assert_eq!(client.contract_event_count(&other), 0);
    }

    #[test]
    fn test_contract_event_types() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);

        client.add_indexer(&admin, &indexer);

        // Initially empty
        let types = client.contract_event_types(&target);
        assert_eq!(types.len(), 0);

        // Record a swap event
        client.record_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
        );
        let types = client.contract_event_types(&target);
        assert_eq!(types.len(), 1);
        assert!(types.contains(&symbol_short!("swap")));

        // Record a transfer event
        client.record_event(
            &indexer,
            &target,
            &symbol_short!("transfer"),
            &BytesN::from_array(&env, &[1u8; 32]),
        );
        let types = client.contract_event_types(&target);
        assert_eq!(types.len(), 2);
        assert!(types.contains(&symbol_short!("swap")));
        assert!(types.contains(&symbol_short!("transfer")));

        // Recording duplicate event type does not add it again
        client.record_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[2u8; 32]),
        );
        let types = client.contract_event_types(&target);
        assert_eq!(types.len(), 2);
    }

    #[test]
    fn test_contract_event_types_batch() {
        let env = Env::default();
        env.mock_all_auths();

        let contract_id = env.register_contract(None, SoroScanCore);
        let client = SoroScanCoreClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        let indexer = Address::generate(&env);
        let target1 = Address::generate(&env);
        let target2 = Address::generate(&env);

        client.init(&admin);
        client.add_indexer(&admin, &indexer);

        // Batch events for two different contracts
        let mut entries = Vec::new(&env);
        entries.push_back(EventEntry {
            contract_id: target1.clone(),
            event_type: symbol_short!("swap"),
            payload_hash: BytesN::from_array(&env, &[1u8; 32]),
        });
        entries.push_back(EventEntry {
            contract_id: target1.clone(),
            event_type: symbol_short!("mint"),
            payload_hash: BytesN::from_array(&env, &[2u8; 32]),
        });
        entries.push_back(EventEntry {
            contract_id: target2.clone(),
            event_type: symbol_short!("transfer"),
            payload_hash: BytesN::from_array(&env, &[3u8; 32]),
        });

        client.record_events_batch(&indexer, &entries);

        assert_eq!(client.contract_event_count(&target1), 2);
        assert_eq!(client.contract_event_count(&target2), 1);

        let types1 = client.contract_event_types(&target1);
        assert_eq!(types1.len(), 2);
        assert!(types1.contains(&symbol_short!("swap")));
        assert!(types1.contains(&symbol_short!("mint")));

        let types2 = client.contract_event_types(&target2);
        assert_eq!(types2.len(), 1);
        assert!(types2.contains(&symbol_short!("transfer")));
    }

    #[test]
    fn test_contract_event_count_multiple_contracts() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target_a = Address::generate(&env);
        let target_b = Address::generate(&env);

        client.add_indexer(&admin, &indexer);

        client.record_event(
            &indexer,
            &target_a,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
        );
        client.record_event(
            &indexer,
            &target_a,
            &symbol_short!("transfer"),
            &BytesN::from_array(&env, &[1u8; 32]),
        );
        client.record_event(
            &indexer,
            &target_b,
            &symbol_short!("mint"),
            &BytesN::from_array(&env, &[2u8; 32]),
        );

        assert_eq!(client.contract_event_count(&target_a), 2);
        assert_eq!(client.contract_event_count(&target_b), 1);
    }

    #[test]
    fn test_event_decoding_and_types() {
        use soroban_sdk::{TryFromVal, Val};

        let env = Env::default();
        let _contract_id = env.register_contract(None, SoroScanCore);

        // Define complex variables of 10+ Soroban types:
        let val_bool: bool = true;
        let val_u32: u32 = 42;
        let val_i32: i32 = -42;
        let val_u64: u64 = 1000000;
        let val_i64: i64 = -1000000;
        let val_u128: u128 = 12345678901234567890;
        let val_i128: i128 = -12345678901234567890;
        let val_symbol = symbol_short!("test");
        let val_address = Address::generate(&env);

        let mut val_bytes = soroban_sdk::Bytes::new(&env);
        val_bytes.append(&soroban_sdk::Bytes::from_array(&env, &[1, 2, 3]));

        let val_bytes_n = BytesN::from_array(&env, &[9u8; 32]);

        let mut val_map = Map::<Symbol, u32>::new(&env);
        val_map.set(symbol_short!("key1"), 100);
        val_map.set(symbol_short!("key2"), 200);

        let mut val_vec = soroban_sdk::Vec::<Symbol>::new(&env);
        val_vec.push_back(symbol_short!("item1"));
        val_vec.push_back(symbol_short!("item2"));

        // Emitting events with various topics and payloads to test topic extraction and symbol parsing
        // Event 1: Testing simple types
        env.events().publish(
            (symbol_short!("event1"), val_symbol.clone(), val_bool),
            (val_u32, val_i32, val_u64, val_i64),
        );

        // Event 2: Testing large integers and Address
        env.events().publish(
            (symbol_short!("event2"), val_address.clone()),
            (val_u128, val_i128),
        );

        // Event 3: Testing Bytes, BytesN, Map, Vec
        env.events().publish(
            (symbol_short!("event3"),),
            (val_bytes.clone(), val_bytes_n.clone(), val_map.clone(), val_vec.clone()),
        );

        // Event 4: Edge case - Empty topics (Note: Soroban events require at least 1 topic, but we can test emitting a tuple with 1 topic and empty data)
        env.events().publish(
            (symbol_short!("empty"),),
            (),
        );

        // Event 5: Edge case - Large Payload
        let mut large_map = Map::<u32, BytesN<32>>::new(&env);
        for i in 0..10 {
            large_map.set(i, BytesN::from_array(&env, &[i as u8; 32]));
        }
        env.events().publish(
            (symbol_short!("large"),),
            large_map.clone(),
        );

        // Retrieve and decode all published events
        let all_events = env.events().all();
        assert!(all_events.len() >= 5);

        // Find the event with topic "event1"
        // Note: `env.events().all()` returns `(Address, Vec<Val>, Val)` tuples
        // in this soroban-sdk version, so topics/value are accessed positionally
        // (`.1` = topics, `.2` = payload value) rather than by named field.
        let event1 = all_events.iter().find(|e| {
            if e.1.len() > 0 {
                if let Ok(sym) = Symbol::try_from_val(&env, &e.1.get(0).unwrap()) {
                    return sym == symbol_short!("event1");
                }
            }
            false
        }).expect("event1 should exist");

        // Verify topic extraction
        assert_eq!(event1.1.len(), 3);
        let extracted_sym = Symbol::try_from_val(&env, &event1.1.get(1).unwrap()).unwrap();
        assert_eq!(extracted_sym, val_symbol);
        let extracted_bool = bool::try_from_val(&env, &event1.1.get(2).unwrap()).unwrap();
        assert_eq!(extracted_bool, val_bool);

        // Verify payload decoding
        let payload1: (u32, i32, u64, i64) = TryFromVal::try_from_val(&env, &event1.2).unwrap();
        assert_eq!(payload1.0, val_u32);
        assert_eq!(payload1.1, val_i32);
        assert_eq!(payload1.2, val_u64);
        assert_eq!(payload1.3, val_i64);

        // Find event2
        let event2 = all_events.iter().find(|e| {
            if e.1.len() > 0 {
                if let Ok(sym) = Symbol::try_from_val(&env, &e.1.get(0).unwrap()) {
                    return sym == symbol_short!("event2");
                }
            }
            false
        }).expect("event2 should exist");

        let extracted_addr = Address::try_from_val(&env, &event2.1.get(1).unwrap()).unwrap();
        assert_eq!(extracted_addr, val_address);

        let payload2: (u128, i128) = TryFromVal::try_from_val(&env, &event2.2).unwrap();
        assert_eq!(payload2.0, val_u128);
        assert_eq!(payload2.1, val_i128);

        // Find event3
        let event3 = all_events.iter().find(|e| {
            if e.1.len() > 0 {
                if let Ok(sym) = Symbol::try_from_val(&env, &e.1.get(0).unwrap()) {
                    return sym == symbol_short!("event3");
                }
            }
            false
        }).expect("event3 should exist");

        let payload3: (soroban_sdk::Bytes, BytesN<32>, Map<Symbol, u32>, soroban_sdk::Vec<Symbol>) =
            TryFromVal::try_from_val(&env, &event3.2).unwrap();
        assert_eq!(payload3.0, val_bytes);
        assert_eq!(payload3.1, val_bytes_n);
        assert_eq!(payload3.2.get(symbol_short!("key1")).unwrap(), 100);
        assert_eq!(payload3.3.get(0).unwrap(), symbol_short!("item1"));

        // Find empty event
        let event_empty = all_events.iter().find(|e| {
            if e.1.len() > 0 {
                if let Ok(sym) = Symbol::try_from_val(&env, &e.1.get(0).unwrap()) {
                    return sym == symbol_short!("empty");
                }
            }
            false
        }).expect("empty event should exist");
        assert_eq!(event_empty.1.len(), 1); // just "empty"

        // Find large event
        let event_large = all_events.iter().find(|e| {
            if e.1.len() > 0 {
                if let Ok(sym) = Symbol::try_from_val(&env, &e.1.get(0).unwrap()) {
                    return sym == symbol_short!("large");
                }
            }
            false
        }).expect("large event should exist");
        let payload_large: Map<u32, BytesN<32>> = TryFromVal::try_from_val(&env, &event_large.2).unwrap();
        assert_eq!(payload_large.len(), 10);
        assert_eq!(payload_large.get(5).unwrap(), BytesN::from_array(&env, &[5u8; 32]));
    }

    // ── SC-10: pause/resume indexer ─────────────────────────────────────────

    #[test]
    fn test_pause_and_resume_indexer() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        client.add_indexer(&admin, &indexer);

        // Initially active
        assert_eq!(client.get_indexer_status(&indexer), Some(IndexerStatus::Active));
        assert!(client.is_indexer(&indexer));

        // Pause
        client.pause_indexer(&admin, &indexer);
        assert_eq!(client.get_indexer_status(&indexer), Some(IndexerStatus::Paused));
        // is_indexer returns false for paused indexers
        assert!(!client.is_indexer(&indexer));

        // Resume
        client.resume_indexer(&admin, &indexer);
        assert_eq!(client.get_indexer_status(&indexer), Some(IndexerStatus::Active));
        assert!(client.is_indexer(&indexer));
    }

    #[test]
    fn test_paused_indexer_cannot_record_event() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);

        client.add_indexer(&admin, &indexer);
        client.pause_indexer(&admin, &indexer);

        let result = client.try_record_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
        );
        assert_eq!(result, Err(Ok(ContractError::IndexerPaused)));
        assert_eq!(client.total_events(), 0);
    }

    #[test]
    fn test_paused_indexer_cannot_record_batch() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        client.add_indexer(&admin, &indexer);
        client.pause_indexer(&admin, &indexer);

        let mut entries = Vec::new(&env);
        entries.push_back(EventEntry {
            contract_id: Address::generate(&env),
            event_type: symbol_short!("swap"),
            payload_hash: BytesN::from_array(&env, &[0u8; 32]),
        });

        let result = client.try_record_events_batch(&indexer, &entries);
        assert_eq!(result, Err(Ok(ContractError::IndexerPaused)));
    }

    #[test]
    fn test_pause_indexer_unauthorized() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let non_admin = Address::generate(&env);
        client.add_indexer(&admin, &indexer);

        let result = client.try_pause_indexer(&non_admin, &indexer);
        assert_eq!(result, Err(Ok(ContractError::Unauthorized)));
        // Still active
        assert_eq!(client.get_indexer_status(&indexer), Some(IndexerStatus::Active));
    }

    #[test]
    fn test_pause_nonexistent_indexer() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, _) = setup_contract(&env);
        let ghost = Address::generate(&env);

        let result = client.try_pause_indexer(&admin, &ghost);
        assert_eq!(result, Err(Ok(ContractError::IndexerNotFound)));
    }

    #[test]
    fn test_get_indexer_status_unknown() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, _, _) = setup_contract(&env);
        let unknown = Address::generate(&env);

        assert_eq!(client.get_indexer_status(&unknown), None);
    }

    #[test]
    fn test_resumed_indexer_can_record_event() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);

        client.add_indexer(&admin, &indexer);
        client.pause_indexer(&admin, &indexer);
        client.resume_indexer(&admin, &indexer);

        let count = client.record_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
        );
        assert_eq!(count, 1);
    }

    // ── SC-38 / SC-42: structured events and revocation ─────────────────────

    fn corr(env: &Env, byte: u8) -> BytesN<32> {
        BytesN::from_array(env, &[byte; 32])
    }

    #[test]
    fn test_record_structured_event() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        client.add_indexer(&admin, &indexer);

        let correlation_id = corr(&env, 1);
        let count = client.record_structured_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
            &1u32,
            &correlation_id,
        );
        assert_eq!(count, 1);

        let record = client
            .structured_by_correlation(&correlation_id)
            .expect("record should exist");
        assert_eq!(record.contract_id, target);
        assert_eq!(record.schema_version, 1);
        assert!(!record.revoked);
        assert!(!client.is_structured_event_revoked(&correlation_id));
    }

    #[test]
    fn test_record_structured_event_rejects_zero_schema_version() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        client.add_indexer(&admin, &indexer);

        let result = client.try_record_structured_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
            &0u32,
            &corr(&env, 2),
        );
        assert_eq!(result, Err(Ok(ContractError::InvalidSchemaVersion)));
    }

    #[test]
    fn test_record_structured_event_rejects_duplicate_correlation() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        client.add_indexer(&admin, &indexer);

        let correlation_id = corr(&env, 3);
        client.record_structured_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
            &1u32,
            &correlation_id,
        );

        let result = client.try_record_structured_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[1u8; 32]),
            &1u32,
            &correlation_id,
        );
        assert_eq!(result, Err(Ok(ContractError::DuplicateCorrelation)));
    }

    #[test]
    fn test_paused_indexer_cannot_record_structured_event() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        client.add_indexer(&admin, &indexer);
        client.pause_indexer(&admin, &indexer);

        let result = client.try_record_structured_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
            &1u32,
            &corr(&env, 4),
        );
        assert_eq!(result, Err(Ok(ContractError::IndexerPaused)));
    }

    #[test]
    fn test_revoke_structured_event() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        client.add_indexer(&admin, &indexer);

        let correlation_id = corr(&env, 5);
        client.record_structured_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
            &1u32,
            &correlation_id,
        );

        assert!(!client.is_structured_event_revoked(&correlation_id));

        client.revoke_structured_event(&indexer, &correlation_id);

        assert!(client.is_structured_event_revoked(&correlation_id));
        let record = client.structured_by_correlation(&correlation_id).unwrap();
        assert!(record.revoked);
    }

    #[test]
    fn test_revoke_structured_event_updates_latest_by_type_projection() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        client.add_indexer(&admin, &indexer);

        let correlation_id = corr(&env, 6);
        client.record_structured_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
            &1u32,
            &correlation_id,
        );

        client.revoke_structured_event(&indexer, &correlation_id);

        // Recording a second event for the same type should not be affected
        // by the revocation of the first.
        let other_correlation = corr(&env, 7);
        client.record_structured_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[1u8; 32]),
            &1u32,
            &other_correlation,
        );
        assert!(!client.is_structured_event_revoked(&other_correlation));
    }

    #[test]
    fn test_revoke_structured_event_twice_fails() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        client.add_indexer(&admin, &indexer);

        let correlation_id = corr(&env, 8);
        client.record_structured_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
            &1u32,
            &correlation_id,
        );
        client.revoke_structured_event(&indexer, &correlation_id);

        let result = client.try_revoke_structured_event(&indexer, &correlation_id);
        assert_eq!(result, Err(Ok(ContractError::AlreadyRevoked)));
    }

    #[test]
    fn test_revoke_nonexistent_structured_event() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        client.add_indexer(&admin, &indexer);

        let result = client.try_revoke_structured_event(&indexer, &corr(&env, 9));
        assert_eq!(result, Err(Ok(ContractError::StructuredEventNotFound)));
    }

    #[test]
    fn test_revoke_structured_event_unauthorized_indexer() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        let rogue = Address::generate(&env);
        client.add_indexer(&admin, &indexer);

        let correlation_id = corr(&env, 10);
        client.record_structured_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
            &1u32,
            &correlation_id,
        );

        let result = client.try_revoke_structured_event(&rogue, &correlation_id);
        assert_eq!(result, Err(Ok(ContractError::IndexerNotFound)));
    }

    #[test]
    fn test_revoke_structured_event_paused_indexer() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        client.add_indexer(&admin, &indexer);

        let correlation_id = corr(&env, 11);
        client.record_structured_event(
            &indexer,
            &target,
            &symbol_short!("swap"),
            &BytesN::from_array(&env, &[0u8; 32]),
            &1u32,
            &correlation_id,
        );

        client.pause_indexer(&admin, &indexer);

        let result = client.try_revoke_structured_event(&indexer, &correlation_id);
        assert_eq!(result, Err(Ok(ContractError::IndexerPaused)));
    }

    #[test]
    fn test_is_structured_event_revoked_missing_returns_error() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, _admin, _indexer) = setup_contract(&env);
        let result = client.try_is_structured_event_revoked(&corr(&env, 12));
        assert_eq!(result, Err(Ok(ContractError::StructuredEventNotFound)));
    }
}
