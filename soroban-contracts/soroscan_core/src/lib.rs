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
/// Per-indexer configured rate limits (SC-26).
const RATE_LIMITS_KEY: Symbol = symbol_short!("ratelim");
/// Per-indexer current-ledger usage counters (SC-26).
const RATE_USAGE_KEY: Symbol = symbol_short!("rateuse");

/// Storage keys for structured (SC-38) event records that need a
/// non-`Symbol` discriminant (correlation IDs are 32 raw bytes).
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DataKey {
    /// Look up a structured event by its idempotency/correlation id.
    StructuredByCorrelation(BytesN<32>),
    /// Look up the latest structured event recorded for an event type.
    LatestStructuredByType(Symbol),
}

/// A versioned, correlation-tagged event record (SC-38).
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct StructuredEventRecord {
    /// The contract that emitted the original event.
    pub contract_id: Address,
    /// The type/category of the event.
    pub event_type: Symbol,
    /// SHA-256 hash of the event payload for verification.
    pub payload_hash: BytesN<32>,
    /// Producer-defined schema version for the payload.
    pub schema_version: u32,
    /// Idempotency key used to make producer retries safe.
    pub correlation_id: BytesN<32>,
    /// Ledger sequence number when recorded.
    pub ledger: u32,
    /// Unix timestamp when recorded.
    pub timestamp: u64,
}

/// Tracks how many events an indexer has recorded within a given ledger,
/// used to enforce per-ledger rate limits (SC-26).
#[contracttype]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RateLimitUsage {
    /// The ledger sequence this usage count applies to.
    pub ledger: u32,
    /// Number of events recorded by the indexer in `ledger` so far.
    pub count: u32,
}

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
    /// The provided schema version is invalid (must be >= 1) (SC-38).
    InvalidSchemaVersion = 7,
    /// A structured event with this correlation id was already recorded (SC-38).
    DuplicateCorrelation = 8,
    /// The indexer has exceeded its configured per-ledger event limit (SC-26).
    RateLimitExceeded = 9,
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

        match indexers.get(indexer.clone()) {
            Some(IndexerStatus::Active) => {}
            Some(IndexerStatus::Paused) => return Err(ContractError::IndexerPaused),
            None => return Err(ContractError::IndexerNotFound),
        }

        Self::enforce_rate_limit(&env, &indexer, 1)?;

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

        match indexers.get(indexer.clone()) {
            Some(IndexerStatus::Active) => {}
            Some(IndexerStatus::Paused) => return Err(ContractError::IndexerPaused),
            None => return Err(ContractError::IndexerNotFound),
        }

        Self::enforce_rate_limit(&env, &indexer, 1)?;

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

        Self::enforce_rate_limit(&env, &indexer, batch_len)?;

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

    /// Set (or clear) the maximum number of events an indexer may record
    /// within a single ledger (SC-26). Admin only.
    ///
    /// Passing `max_events_per_ledger == 0` removes any configured limit,
    /// restoring unlimited (default) throughput for that indexer.
    ///
    /// # Arguments
    /// * `env` - The contract environment
    /// * `admin` - The admin address (must match stored admin)
    /// * `indexer` - The indexer address to configure
    /// * `max_events_per_ledger` - Max events per ledger, or 0 for unlimited
    pub fn set_indexer_rate_limit(
        env: Env,
        admin: Address,
        indexer: Address,
        max_events_per_ledger: u32,
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

        let mut limits: Map<Address, u32> = env
            .storage()
            .instance()
            .get(&RATE_LIMITS_KEY)
            .unwrap_or(Map::new(&env));

        if max_events_per_ledger == 0 {
            limits.remove(indexer.clone());
        } else {
            limits.set(indexer.clone(), max_events_per_ledger);
        }
        env.storage().instance().set(&RATE_LIMITS_KEY, &limits);

        env.events().publish(
            (symbol_short!("ratelim"), symbol_short!("set")),
            (indexer, max_events_per_ledger),
        );

        Ok(())
    }

    /// Get the configured per-ledger rate limit for an indexer (SC-26).
    ///
    /// # Returns
    /// `Some(limit)` if a limit is configured, `None` if the indexer is
    /// unrestricted.
    pub fn get_indexer_rate_limit(env: Env, indexer: Address) -> Option<u32> {
        let limits: Option<Map<Address, u32>> = env.storage().instance().get(&RATE_LIMITS_KEY);
        limits.and_then(|m| m.get(indexer))
    }

    /// Get the number of events an indexer has recorded in the current
    /// ledger so far (SC-26). Returns 0 if the indexer has not recorded any
    /// events in the current ledger.
    pub fn get_indexer_rate_usage(env: Env, indexer: Address) -> u32 {
        let usage: Option<Map<Address, RateLimitUsage>> =
            env.storage().instance().get(&RATE_USAGE_KEY);
        let current_ledger = env.ledger().sequence();
        match usage.and_then(|m| m.get(indexer)) {
            Some(u) if u.ledger == current_ledger => u.count,
            _ => 0,
        }
    }

    /// Check and record usage against an indexer's configured rate limit
    /// (SC-26). No-op if the indexer has no configured limit. Usage counters
    /// automatically reset when the current ledger changes.
    fn enforce_rate_limit(env: &Env, indexer: &Address, amount: u32) -> Result<(), ContractError> {
        let limits: Option<Map<Address, u32>> = env.storage().instance().get(&RATE_LIMITS_KEY);
        let limit = match limits.and_then(|m| m.get(indexer.clone())) {
            Some(limit) => limit,
            None => return Ok(()),
        };

        let current_ledger = env.ledger().sequence();
        let mut usage: Map<Address, RateLimitUsage> = env
            .storage()
            .instance()
            .get(&RATE_USAGE_KEY)
            .unwrap_or(Map::new(env));

        let current_count = match usage.get(indexer.clone()) {
            Some(u) if u.ledger == current_ledger => u.count,
            _ => 0,
        };

        let new_count = current_count.saturating_add(amount);
        if new_count > limit {
            return Err(ContractError::RateLimitExceeded);
        }

        usage.set(
            indexer.clone(),
            RateLimitUsage {
                ledger: current_ledger,
                count: new_count,
            },
        );
        env.storage().instance().set(&RATE_USAGE_KEY, &usage);

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use soroban_sdk::testutils::{Address as _, Events, Ledger};
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
        let event1 = all_events.iter().find(|e| {
            if e.topics.len() > 0 {
                if let Ok(sym) = Symbol::try_from_val(&env, &e.topics.get(0).unwrap()) {
                    return sym == symbol_short!("event1");
                }
            }
            false
        }).expect("event1 should exist");

        // Verify topic extraction
        assert_eq!(event1.topics.len(), 3);
        let extracted_sym = Symbol::try_from_val(&env, &event1.topics.get(1).unwrap()).unwrap();
        assert_eq!(extracted_sym, val_symbol);
        let extracted_bool = bool::try_from_val(&env, &event1.topics.get(2).unwrap()).unwrap();
        assert_eq!(extracted_bool, val_bool);

        // Verify payload decoding
        let payload1: (u32, i32, u64, i64) = TryFromVal::try_from_val(&env, &event1.value).unwrap();
        assert_eq!(payload1.0, val_u32);
        assert_eq!(payload1.1, val_i32);
        assert_eq!(payload1.2, val_u64);
        assert_eq!(payload1.3, val_i64);

        // Find event2
        let event2 = all_events.iter().find(|e| {
            if e.topics.len() > 0 {
                if let Ok(sym) = Symbol::try_from_val(&env, &e.topics.get(0).unwrap()) {
                    return sym == symbol_short!("event2");
                }
            }
            false
        }).expect("event2 should exist");

        let extracted_addr = Address::try_from_val(&env, &event2.topics.get(1).unwrap()).unwrap();
        assert_eq!(extracted_addr, val_address);

        let payload2: (u128, i128) = TryFromVal::try_from_val(&env, &event2.value).unwrap();
        assert_eq!(payload2.0, val_u128);
        assert_eq!(payload2.1, val_i128);

        // Find event3
        let event3 = all_events.iter().find(|e| {
            if e.topics.len() > 0 {
                if let Ok(sym) = Symbol::try_from_val(&env, &e.topics.get(0).unwrap()) {
                    return sym == symbol_short!("event3");
                }
            }
            false
        }).expect("event3 should exist");

        let payload3: (soroban_sdk::Bytes, BytesN<32>, Map<Symbol, u32>, soroban_sdk::Vec<Symbol>) =
            TryFromVal::try_from_val(&env, &event3.value).unwrap();
        assert_eq!(payload3.0, val_bytes);
        assert_eq!(payload3.1, val_bytes_n);
        assert_eq!(payload3.2.get(symbol_short!("key1")).unwrap(), 100);
        assert_eq!(payload3.3.get(0).unwrap(), symbol_short!("item1"));

        // Find empty event
        let event_empty = all_events.iter().find(|e| {
            if e.topics.len() > 0 {
                if let Ok(sym) = Symbol::try_from_val(&env, &e.topics.get(0).unwrap()) {
                    return sym == symbol_short!("empty");
                }
            }
            false
        }).expect("empty event should exist");
        assert_eq!(event_empty.topics.len(), 1); // just "empty"

        // Find large event
        let event_large = all_events.iter().find(|e| {
            if e.topics.len() > 0 {
                if let Ok(sym) = Symbol::try_from_val(&env, &e.topics.get(0).unwrap()) {
                    return sym == symbol_short!("large");
                }
            }
            false
        }).expect("large event should exist");
        let payload_large: Map<u32, BytesN<32>> = TryFromVal::try_from_val(&env, &event_large.value).unwrap();
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

    // ── SC-26: indexer rate limiting ────────────────────────────────────────

    #[test]
    fn test_set_and_get_indexer_rate_limit() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        client.add_indexer(&admin, &indexer);

        assert_eq!(client.get_indexer_rate_limit(&indexer), None);

        client.set_indexer_rate_limit(&admin, &indexer, &5);
        assert_eq!(client.get_indexer_rate_limit(&indexer), Some(5));

        // 0 clears the limit again.
        client.set_indexer_rate_limit(&admin, &indexer, &0);
        assert_eq!(client.get_indexer_rate_limit(&indexer), None);
    }

    #[test]
    fn test_set_indexer_rate_limit_unauthorized() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let non_admin = Address::generate(&env);
        client.add_indexer(&admin, &indexer);

        let result = client.try_set_indexer_rate_limit(&non_admin, &indexer, &5);
        assert_eq!(result, Err(Ok(ContractError::Unauthorized)));
    }

    #[test]
    fn test_unlimited_indexer_can_record_freely() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        client.add_indexer(&admin, &indexer);

        for i in 0..10 {
            client.record_event(
                &indexer,
                &target,
                &symbol_short!("swap"),
                &BytesN::from_array(&env, &[i as u8; 32]),
            );
        }
        assert_eq!(client.total_events(), 10);
    }

    #[test]
    fn test_rate_limited_indexer_blocked_after_limit() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        client.add_indexer(&admin, &indexer);
        client.set_indexer_rate_limit(&admin, &indexer, &2);

        client.record_event(
            &indexer,
            &target,
            &symbol_short!("a"),
            &BytesN::from_array(&env, &[1u8; 32]),
        );
        client.record_event(
            &indexer,
            &target,
            &symbol_short!("b"),
            &BytesN::from_array(&env, &[2u8; 32]),
        );
        assert_eq!(client.get_indexer_rate_usage(&indexer), 2);

        let result = client.try_record_event(
            &indexer,
            &target,
            &symbol_short!("c"),
            &BytesN::from_array(&env, &[3u8; 32]),
        );
        assert_eq!(result, Err(Ok(ContractError::RateLimitExceeded)));
        assert_eq!(client.total_events(), 2);
    }

    #[test]
    fn test_rate_limit_resets_on_new_ledger() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        client.add_indexer(&admin, &indexer);
        client.set_indexer_rate_limit(&admin, &indexer, &1);

        client.record_event(
            &indexer,
            &target,
            &symbol_short!("a"),
            &BytesN::from_array(&env, &[1u8; 32]),
        );
        let blocked = client.try_record_event(
            &indexer,
            &target,
            &symbol_short!("b"),
            &BytesN::from_array(&env, &[2u8; 32]),
        );
        assert_eq!(blocked, Err(Ok(ContractError::RateLimitExceeded)));

        // Advance to the next ledger; usage should reset.
        let next_ledger = env.ledger().sequence() + 1;
        env.ledger().set_sequence_number(next_ledger);

        let count = client.record_event(
            &indexer,
            &target,
            &symbol_short!("c"),
            &BytesN::from_array(&env, &[3u8; 32]),
        );
        assert_eq!(count, 2);
        assert_eq!(client.get_indexer_rate_usage(&indexer), 1);
    }

    #[test]
    fn test_rate_limit_enforced_on_batch() {
        let env = Env::default();
        env.mock_all_auths();

        let contract_id = env.register_contract(None, SoroScanCore);
        let client = SoroScanCoreClient::new(&env, &contract_id);

        let admin = Address::generate(&env);
        let indexer = Address::generate(&env);
        client.init(&admin);
        client.add_indexer(&admin, &indexer);
        client.set_indexer_rate_limit(&admin, &indexer, &2);

        let mut entries = Vec::new(&env);
        for i in 0..3 {
            entries.push_back(EventEntry {
                contract_id: Address::generate(&env),
                event_type: symbol_short!("ev"),
                payload_hash: BytesN::from_array(&env, &[i as u8; 32]),
            });
        }

        // Batch of 3 exceeds the limit of 2; nothing should be recorded.
        let result = client.try_record_events_batch(&indexer, &entries);
        assert_eq!(result, Err(Ok(ContractError::RateLimitExceeded)));
        assert_eq!(client.total_events(), 0);

        // A batch within the limit succeeds.
        let mut small_batch = Vec::new(&env);
        small_batch.push_back(EventEntry {
            contract_id: Address::generate(&env),
            event_type: symbol_short!("ev"),
            payload_hash: BytesN::from_array(&env, &[9u8; 32]),
        });
        let count = client.record_events_batch(&indexer, &small_batch);
        assert_eq!(count, 1);
    }

    #[test]
    fn test_get_indexer_rate_usage_defaults_to_zero() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, _admin, indexer) = setup_contract(&env);
        assert_eq!(client.get_indexer_rate_usage(&indexer), 0);
    }

    #[test]
    fn test_rate_limit_enforced_on_structured_event() {
        let env = Env::default();
        env.mock_all_auths();

        let (client, admin, indexer) = setup_contract(&env);
        let target = Address::generate(&env);
        client.add_indexer(&admin, &indexer);
        client.set_indexer_rate_limit(&admin, &indexer, &1);

        client.record_structured_event(
            &indexer,
            &target,
            &symbol_short!("xfer"),
            &BytesN::from_array(&env, &[1u8; 32]),
            &1u32,
            &BytesN::from_array(&env, &[9u8; 32]),
        );

        let blocked = client.try_record_structured_event(
            &indexer,
            &target,
            &symbol_short!("xfer"),
            &BytesN::from_array(&env, &[2u8; 32]),
            &1u32,
            &BytesN::from_array(&env, &[8u8; 32]),
        );
        assert_eq!(blocked, Err(Ok(ContractError::RateLimitExceeded)));
        assert_eq!(client.total_events(), 1);
    }
}
