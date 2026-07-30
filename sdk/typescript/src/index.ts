export { SoroScanClient, SoroScanError, Paginator } from "./client.js";
export { EventQueryBuilder, ContractQueryBuilder } from "./builder.js";
export { verifyWebhookSignature } from "./webhookVerification.js";
export { WebSocketClient } from "./websocket-client.js";
export type {
  // Config
  SoroScanClientConfig,
  // Shared
  ISODateString,
  ContractId,
  StellarAddress,
  Network,
  LedgerEntryType,
  PageInfo,
  PaginatedResponse,
  // Events
  EventType,
  ContractEventTopic,
  ContractEvent,
  GetEventsParams,
  GetEventsResponse,
  GetEventsByContractsParams,
  GetEventsByContractsResponse,
  RecordStructuredEventParams,
  RecordStructuredEventResponse,
  RevokeStructuredEventParams,
  RevokeStructuredEventResponse,
  // Contracts
  ContractType,
  ContractSpec,
  ContractFunction,
  ContractFunctionParam,
  ContractTypeDefinition,
  Contract,
  GetContractsParams,
  GetContractsResponse,
  GetContractParams,
  // Transactions
  TransactionStatus,
  Transaction,
  GetTransactionsParams,
  GetTransactionsResponse,
  // Ledgers
  Ledger,
  GetLedgersParams,
  GetLedgersResponse,
  // Accounts
  AccountBalance,
  Account,
  GetAccountParams,
  // Webhooks
  WebhookTrigger,
  WebhookStatus,
  Webhook,
  SubscribeWebhookParams,
  UpdateWebhookParams,
  WebhookListResponse,
  // SC-17: Contract event type info
  ContractEventTypeInfo,
  // SC-29: Batch event recording
  EventEntry,
  RecordEventsBatchParams,
  RecordEventsBatchResponse,
  // WebSocket
  WebSocketClientConfig,
  EventCallback,
  ConnectionCallback,
  ErrorCallback,
  ReconnectingCallback,
  EventFilter,
  // Errors
  SoroScanApiError,
} from "./types.js";
