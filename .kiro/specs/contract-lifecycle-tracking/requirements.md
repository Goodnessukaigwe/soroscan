# Requirements Document

## Introduction

SoroScan currently indexes events and invocations for Soroban smart contracts but does not track the broader lifecycle of a contract — from initial deployment through upgrades, pauses, resumes, and eventual destruction. This feature adds contract lifecycle tracking to enable developers and auditors to understand a contract's maturity, version history, and operational state over time.

The system will introduce a `ContractLifecycleEvent` model that records discrete lifecycle transitions, expose a GraphQL query for retrieving a contract's full timeline, provide a timeline visualization in the UI, and allow administrators to manually log lifecycle events via the Django admin interface.

## Glossary

- **TrackedContract**: An existing SoroScan model representing a Soroban smart contract indexed by the platform.
- **ContractLifecycleEvent**: A record of a single lifecycle transition for a TrackedContract, including event type, WASM hash, and ledger-verified timestamp.
- **Lifecycle_Store**: The database persistence layer for ContractLifecycleEvent records.
- **Event_Type**: An enumerated value representing the kind of lifecycle transition: `deployed`, `upgraded`, `paused`, `resumed`, or `destroyed`.
- **WASM_Hash**: A 64-character hex string identifying the compiled WASM bytecode associated with a deployment or upgrade event.
- **Timeline**: An ordered sequence of ContractLifecycleEvent records for a single TrackedContract, sorted by timestamp ascending.
- **Ledger_Timestamp**: A timestamp that has been verified against the Stellar ledger to confirm it falls within a valid ledger close time.
- **GraphQL_API**: The existing SoroScan GraphQL endpoint through which lifecycle data is exposed.
- **Admin_Interface**: The Django admin UI used by SoroScan administrators to manage platform data.
- **Lifecycle_Serializer**: The component that converts ContractLifecycleEvent model instances to JSON for API responses.
- **Migration_Tool**: The Django migration system responsible for applying schema changes to the database.

---

## Requirements

### Requirement 1: ContractLifecycleEvent Model

**User Story:** As a developer, I want lifecycle events persisted in the database, so that I can query the full history of a contract's operational state.

#### Acceptance Criteria

1. THE Lifecycle_Store SHALL persist ContractLifecycleEvent records with fields: contract (FK to TrackedContract), event_type, wasm_hash, created_at, and ledger_sequence.
2. THE Lifecycle_Store SHALL restrict event_type to the enumerated values: `deployed`, `upgraded`, `paused`, `resumed`, `destroyed`.
3. THE Lifecycle_Store SHALL allow wasm_hash to be blank for event types other than `deployed` and `upgraded`.
4. THE Lifecycle_Store SHALL create a database index on (contract, created_at) for efficient timeline queries.
5. THE Lifecycle_Store SHALL enforce that created_at is a non-null datetime field.
6. WHEN a ContractLifecycleEvent is persisted, THE Lifecycle_Store SHALL store the record as immutable — no update operations SHALL be permitted on existing records.

---

### Requirement 2: Ledger Timestamp Verification

**User Story:** As an auditor, I want lifecycle event timestamps verified against the ledger, so that I can trust the accuracy of the audit trail.

#### Acceptance Criteria

1. WHEN a ContractLifecycleEvent is created, THE Lifecycle_Store SHALL verify that the provided created_at timestamp falls within the close time of the specified ledger_sequence.
2. IF the provided created_at timestamp does not correspond to the specified ledger_sequence, THEN THE Lifecycle_Store SHALL reject the record and return a descriptive validation error.
3. IF the specified ledger_sequence does not exist in the SoroScan ledger index, THEN THE Lifecycle_Store SHALL reject the record and return a descriptive validation error.

---

### Requirement 3: Database Migration

**User Story:** As a developer, I want a database migration created, so that the ContractLifecycleEvent model is added to the schema without manual intervention.

#### Acceptance Criteria

1. THE Migration_Tool SHALL generate a Django migration file that creates the ContractLifecycleEvent table with all specified fields.
2. THE Migration_Tool SHALL create the database index on (contract, created_at) in the migration.
3. THE Migration_Tool SHALL define the ForeignKey from ContractLifecycleEvent to TrackedContract with CASCADE delete behavior.
4. WHEN the migration is applied, THE Migration_Tool SHALL complete without errors on an existing database.

---

### Requirement 4: Admin Interface for Manual Event Logging

**User Story:** As an administrator, I want to manually log lifecycle events via the admin UI, so that I can record events that were not automatically captured.

#### Acceptance Criteria

1. THE Admin_Interface SHALL register ContractLifecycleEvent with the Django admin site.
2. THE Admin_Interface SHALL display ContractLifecycleEvent records in a list view showing contract, event_type, wasm_hash, ledger_sequence, and created_at columns.
3. THE Admin_Interface SHALL allow administrators to create new ContractLifecycleEvent records via the admin add form.
4. THE Admin_Interface SHALL apply ledger timestamp verification when an administrator submits a new record through the admin form.
5. IF ledger timestamp verification fails, THEN THE Admin_Interface SHALL display the validation error inline on the admin form without saving the record.
6. THE Admin_Interface SHALL make ContractLifecycleEvent records read-only after creation to preserve the immutable audit trail.

---

### Requirement 5: GraphQL Query for Contract Lifecycle Timeline

**User Story:** As a frontend developer, I want a GraphQL query to retrieve a contract's lifecycle timeline, so that I can build timeline visualizations efficiently.

#### Acceptance Criteria

1. THE GraphQL_API SHALL provide a query `contractLifecycle(contractId: String!)` that returns an ordered list of ContractLifecycleEvent records for the specified contract.
2. WHEN the query is executed, THE GraphQL_API SHALL return events ordered by created_at ascending.
3. WHEN the query is executed, THE GraphQL_API SHALL return the following fields per event: id, eventType, wasmHash, ledgerSequence, createdAt.
4. IF the specified contractId does not correspond to a known TrackedContract, THEN THE GraphQL_API SHALL return a null result with a descriptive error message.
5. THE GraphQL_API SHALL define a `ContractLifecycleEvent` GraphQL type with fields matching the model.
6. THE GraphQL_API SHALL support an optional `eventType` filter argument on the `contractLifecycle` query to return only events of a specified type.

---

### Requirement 6: Timeline Visualization

**User Story:** As a developer, I want a visual timeline of a contract's lifecycle events, so that I can quickly understand the contract's history and current state.

#### Acceptance Criteria

1. THE Timeline SHALL render each ContractLifecycleEvent as a distinct entry showing event_type, created_at, and wasm_hash (when present).
2. THE Timeline SHALL display events in chronological order, oldest first.
3. THE Timeline SHALL visually distinguish each Event_Type using a consistent color or icon scheme.
4. WHEN a contract has no lifecycle events, THE Timeline SHALL display a message indicating no lifecycle history is available.
5. THE Timeline SHALL be accessible at the contract detail page for each TrackedContract.
6. WHEN the `contractLifecycle` GraphQL query returns data, THE Timeline SHALL render without requiring a page reload.

---

### Requirement 7: Lifecycle Serializer

**User Story:** As a backend developer, I want a serializer for ContractLifecycleEvent, so that I can convert model instances to JSON for API responses.

#### Acceptance Criteria

1. THE Lifecycle_Serializer SHALL serialize all ContractLifecycleEvent fields to JSON: id, event_type, wasm_hash, ledger_sequence, created_at.
2. THE Lifecycle_Serializer SHALL format created_at as an ISO 8601 timestamp string.
3. THE Lifecycle_Serializer SHALL include a nested contract field containing the TrackedContract's contract_id and name.
4. THE Lifecycle_Serializer SHALL omit wasm_hash from the output when the field is blank.

---

### Requirement 8: WASM Hash Validation

**User Story:** As a developer, I want WASM hashes validated on input, so that invalid hashes are rejected before being stored.

#### Acceptance Criteria

1. WHEN a ContractLifecycleEvent with event_type `deployed` or `upgraded` is created, THE Lifecycle_Store SHALL require wasm_hash to be non-blank.
2. IF a wasm_hash value is provided, THEN THE Lifecycle_Store SHALL validate that it is exactly 64 hexadecimal characters.
3. IF a wasm_hash fails validation, THEN THE Lifecycle_Store SHALL reject the record and return a descriptive validation error identifying the invalid field.
