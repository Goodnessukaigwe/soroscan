'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';
import { Spinner } from '@/components/ui/spinner';

export interface VerificationRequestData {
  contractId: string;
  sourceCode: string;
  compilerVersion: string;
  optimizationEnabled: boolean;
  notes: string;
}

export interface VerificationRequestFormProps {
  contractId: string;
  onSubmit: (data: VerificationRequestData) => Promise<void>;
  className?: string;
}

export function VerificationRequestForm({
  contractId,
  onSubmit,
  className,
}: VerificationRequestFormProps) {
  const [sourceCode, setSourceCode] = React.useState('');
  const [compilerVersion, setCompilerVersion] = React.useState('');
  const [optimizationEnabled, setOptimizationEnabled] = React.useState(true);
  const [notes, setNotes] = React.useState('');
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [submitted, setSubmitted] = React.useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!sourceCode.trim()) {
      setError('Source code is required.');
      return;
    }
    if (!compilerVersion.trim()) {
      setError('Compiler version is required.');
      return;
    }

    setIsSubmitting(true);
    try {
      await onSubmit({
        contractId,
        sourceCode,
        compilerVersion,
        optimizationEnabled,
        notes,
      });
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div
        className="flex flex-col items-center justify-center py-10 gap-3 text-center"
        data-testid="verification-request-success"
      >
        <span className="text-3xl" aria-hidden="true">✓</span>
        <p className="text-sm font-mono text-green-400">
          Verification request submitted successfully.
        </p>
        <p className="text-xs text-gray-500 font-mono">
          The registry will verify your source code against the on-chain bytecode.
          This may take a few minutes.
        </p>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={cn('space-y-4', className)}
      data-testid="verification-request-form"
      aria-label="Request contract verification"
    >
      <div>
        <label
          htmlFor="vrf-compiler-version"
          className="block text-xs font-mono text-gray-400 mb-1"
        >
          Compiler version <span aria-hidden="true">*</span>
        </label>
        <input
          id="vrf-compiler-version"
          type="text"
          required
          placeholder="e.g. 1.79.0"
          value={compilerVersion}
          onChange={(e) => setCompilerVersion(e.target.value)}
          data-testid="vrf-compiler-version"
          className="w-full h-9 px-3 text-sm font-mono bg-gray-900 border border-gray-700 rounded text-gray-200 placeholder-gray-600 focus:outline-none focus:border-green-600"
        />
      </div>

      <div className="flex items-center gap-2">
        <input
          id="vrf-optimization"
          type="checkbox"
          checked={optimizationEnabled}
          onChange={(e) => setOptimizationEnabled(e.target.checked)}
          data-testid="vrf-optimization-checkbox"
          className="w-4 h-4 accent-green-500"
        />
        <label
          htmlFor="vrf-optimization"
          className="text-xs font-mono text-gray-400 cursor-pointer"
        >
          Compiled with optimizations
        </label>
      </div>

      <div>
        <label
          htmlFor="vrf-source-code"
          className="block text-xs font-mono text-gray-400 mb-1"
        >
          Source code (.rs) <span aria-hidden="true">*</span>
        </label>
        <textarea
          id="vrf-source-code"
          required
          rows={10}
          placeholder="Paste your Rust source code here…"
          value={sourceCode}
          onChange={(e) => setSourceCode(e.target.value)}
          data-testid="vrf-source-code"
          className="w-full px-3 py-2 text-xs font-mono bg-gray-900 border border-gray-700 rounded text-gray-200 placeholder-gray-600 focus:outline-none focus:border-green-600 resize-y"
        />
      </div>

      <div>
        <label
          htmlFor="vrf-notes"
          className="block text-xs font-mono text-gray-400 mb-1"
        >
          Notes (optional)
        </label>
        <textarea
          id="vrf-notes"
          rows={3}
          placeholder="Any additional context for the verifier…"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          data-testid="vrf-notes"
          className="w-full px-3 py-2 text-xs font-mono bg-gray-900 border border-gray-700 rounded text-gray-200 placeholder-gray-600 focus:outline-none focus:border-green-600 resize-y"
        />
      </div>

      {error && (
        <div
          role="alert"
          className="text-xs font-mono text-red-400 border border-red-800 bg-red-900/20 rounded px-3 py-2"
          data-testid="vrf-error"
        >
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={isSubmitting}
        data-testid="vrf-submit-button"
        className="w-full h-9 px-4 text-sm font-mono rounded border border-green-700 bg-green-900/20 text-green-400 hover:bg-green-900/40 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
      >
        {isSubmitting && <Spinner size="mini" color="success" label="Submitting..." />}
        {isSubmitting ? 'Submitting…' : 'Submit for Verification'}
      </button>
    </form>
  );
}
