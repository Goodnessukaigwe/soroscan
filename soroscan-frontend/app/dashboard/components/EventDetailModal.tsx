'use client';

import { useState } from 'react';

import { CopyEventLink } from '@/components/events/CopyEventLink';
import { formatDateTime } from '@/components/ingest/formatters';
import type { EventRecord } from '@/components/ingest/types';
import styles from '@/components/ingest/ingest-terminal.module.css';

import { JsonHighlight } from './JsonHighlight';

interface EventDetailModalProps {
  event: EventRecord;
  onClose: () => void;
}

export function EventDetailModal({ event, onClose }: EventDetailModalProps) {
  const [copied, setCopied] = useState<string | null>(null);
  const [payloadView, setPayloadView] = useState<'json' | 'hex'>('json');

  const payloadJson = JSON.stringify(event.payload, null, 2);
  const payloadHex = toHex(payloadJson);

  const copyToClipboard = async (text: string, label: string): Promise<void> => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(label);

      setTimeout(() => {
        setCopied(null);
      }, 2000);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  const handleOverlayClick = (eventClick: React.MouseEvent<HTMLDivElement>): void => {
    if (eventClick.target === eventClick.currentTarget) {
      onClose();
    }
  };

  return (
    <div className={styles.exportModalOverlay} onClick={handleOverlayClick}>
      <div
        className={styles.exportModal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="event-details-title"
      >
        <div className={styles.exportModalHead}>
          <h2 id="event-details-title" className={styles.exportModalTitle}>
            Event Details
          </h2>

          <button
            type="button"
            className={styles.modalIconBtn}
            onClick={onClose}
            aria-label="Close event details"
          >
            ✕
          </button>
        </div>

        <div className={styles.exportModalBody}>
          <div
            style={{
              display: 'grid',
              gap: '1rem',
            }}
          >
            <section
              style={{
                border: '1px solid rgba(0, 212, 255, 0.2)',
                borderRadius: '6px',
                padding: '0.75rem',
                display: 'grid',
                gap: '0.55rem',
              }}
            >
              <h3
                style={{
                  margin: 0,
                  color: '#00d4ff',
                  fontSize: '0.9rem',
                }}
              >
                Metadata
              </h3>

              <div
                style={{
                  display: 'grid',
                  gap: '0.55rem',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                }}
              >
                <MetaBadge label="Timestamp" value={formatDateTime(event.timestamp)} />

                <MetaBadge label="Ledger" value={event.ledger.toString()} />

                <MetaBadge label="Event Index" value={event.eventIndex.toString()} />

                <MetaBadge label="Event Type" value={event.eventType} />
              </div>
            </section>

            <DetailRow
              label="Event ID"
              value={event.id}
              onCopy={() => {
                void copyToClipboard(event.id, 'id');
              }}
              copied={copied === 'id'}
            />

            <DetailRow
              label="Contract ID"
              value={event.contractId}
              onCopy={() => {
                void copyToClipboard(event.contractId, 'contract');
              }}
              copied={copied === 'contract'}
            />

            {event.contractName ? (
              <DetailRow label="Contract Name" value={event.contractName} />
            ) : null}

            <DetailRow
              label="Transaction Hash"
              value={event.txHash}
              onCopy={() => {
                void copyToClipboard(event.txHash, 'tx');
              }}
              copied={copied === 'tx'}
            />

            <div>
              <div
                style={{
                  marginBottom: '0.5rem',
                }}
              >
                <span className={styles.fieldLabel}>Payload</span>

                <div
                  style={{
                    display: 'flex',
                    gap: '0.35rem',
                    flexWrap: 'wrap',
                  }}
                >
                  <button
                    type="button"
                    className={`${styles.btn} ${payloadView === 'json' ? '' : styles.secondaryBtn}`}
                    style={{
                      padding: '0.25rem 0.55rem',
                      fontSize: '0.75rem',
                      minWidth: 'auto',
                    }}
                    onClick={() => {
                      setPayloadView('json');
                    }}
                    aria-label="View payload as JSON"
                    aria-pressed={payloadView === 'json'}
                  >
                    JSON
                  </button>

                  <button
                    type="button"
                    className={`${styles.btn} ${payloadView === 'hex' ? '' : styles.secondaryBtn}`}
                    style={{
                      padding: '0.25rem 0.55rem',
                      fontSize: '0.75rem',
                      minWidth: 'auto',
                    }}
                    onClick={() => {
                      setPayloadView('hex');
                    }}
                    aria-label="View payload as HEX"
                    aria-pressed={payloadView === 'hex'}
                  >
                    HEX
                  </button>

                  <button
                    type="button"
                    className={styles.btn}
                    style={{
                      padding: '0.25rem 0.55rem',
                      fontSize: '0.75rem',
                      minWidth: 'auto',
                    }}
                    aria-label="Copy event payload to clipboard"
                    onClick={() => {
                      void copyToClipboard(
                        payloadView === 'json' ? payloadJson : payloadHex,
                        'payload',
                      );
                    }}
                  >
                    {copied === 'payload' ? 'Copied!' : 'Copy Payload'}
                  </button>
                </div>
              </div>

              {payloadView === 'json' ? (
                <JsonHighlight data={event.payload} theme="dark" maxHeight="300px" />
              ) : (
                <pre
                  style={{
                    background: 'rgba(0, 0, 0, 0.3)',
                    border: '1px solid rgba(0, 212, 255, 0.3)',
                    padding: '0.75rem',
                    borderRadius: '4px',
                    overflow: 'auto',
                    maxHeight: '300px',
                    fontSize: '0.78rem',
                    color: '#ffd27d',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  }}
                >
                  {payloadHex}
                </pre>
              )}
            </div>

            {event.payloadHash ? (
              <DetailRow
                label="Payload Hash"
                value={event.payloadHash}
                onCopy={() => {
                  void copyToClipboard(event.payloadHash ?? '', 'hash');
                }}
                copied={copied === 'hash'}
              />
            ) : null}

            {event.schemaVersion ? (
              <DetailRow label="Schema Version" value={event.schemaVersion} />
            ) : null}

            {event.validationStatus ? (
              <DetailRow label="Validation Status" value={event.validationStatus} />
            ) : null}
          </div>
        </div>

        <div className={styles.exportModalActions}>
          <CopyEventLink eventId={event.id} />

          <button
            type="button"
            className={`${styles.btn} ${styles.secondaryBtn}`}
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function toHex(input: string): string {
  const bytes = new TextEncoder().encode(input);

  return Array.from(bytes)
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join(' ');
}

interface MetaBadgeProps {
  label: string;
  value: string;
}

function MetaBadge({ label, value }: MetaBadgeProps) {
  return (
    <div>
      <span className={styles.fieldLabel}>{label}</span>

      <div
        style={{
          border: '1px solid rgba(123, 168, 181, 0.25)',
          borderRadius: '4px',
          background: 'rgba(0, 0, 0, 0.25)',
          color: '#d6f7ff',
          padding: '0.4rem',
          fontSize: '0.78rem',
          wordBreak: 'break-word',
        }}
      >
        {value}
      </div>
    </div>
  );
}

interface DetailRowProps {
  label: string;
  value: string;
  onCopy?: () => void;
  copied?: boolean;
}

function DetailRow({ label, value, onCopy, copied }: DetailRowProps) {
  return (
    <div>
      <span className={styles.fieldLabel}>{label}</span>

      <div
        style={{
          display: 'flex',
          gap: '0.5rem',
          alignItems: 'center',
        }}
      >
        <code
          style={{
            flex: 1,
            background: 'rgba(0, 0, 0, 0.3)',
            border: '1px solid rgba(123, 168, 181, 0.3)',
            padding: '0.5rem',
            borderRadius: '4px',
            color: '#d6f7ff',
            wordBreak: 'break-all',
            fontSize: '0.8rem',
          }}
        >
          {value}
        </code>

        {onCopy ? (
          <button
            type="button"
            className={styles.btn}
            style={{
              padding: '0.4rem 0.6rem',
              fontSize: '0.75rem',
            }}
            onClick={onCopy}
            aria-label={`Copy ${label}`}
          >
            {copied ? '✓' : '📋'}
          </button>
        ) : null}
      </div>
    </div>
  );
}
