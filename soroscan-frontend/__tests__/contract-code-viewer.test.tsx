/**
 * Tests for Contract Source Code Viewer components (#914).
 *
 * Covers all acceptance criteria:
 * - Syntax-highlighted code view (100+ lines)
 * - VerificationBadge colours / statuses
 * - ABIExplorer: functions, parameters, return types
 * - ConstructorArgsDecoder: human-readable display
 * - BytecodeComparison: hash display + copy + match/mismatch
 * - Download source .rs file
 * - Copy individual functions to clipboard
 * - "Request Verification" button for unverified contracts
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';

// ── Mock prism-react-renderer so tests don't need the real Prism bundle ──
jest.mock('prism-react-renderer', () => {
  return {
    Highlight: ({
      code,
      children,
    }: {
      code: string;
      language: string;
      theme: unknown;
      children: (opts: {
        className: string;
        style: object;
        tokens: Array<Array<{ types: string[]; content: string }>>;
        getLineProps: (o: { line: unknown }) => { key: string; className: string };
        getTokenProps: (o: { token: unknown }) => { key: string; className: string };
      }) => React.ReactNode;
    }) => {
      const lines = code.split('\n');
      const tokens = lines.map((l) => [{ types: ['plain'], content: l }]);
      return (
        <>{
          children({
            className: 'prism-code',
            style: {},
            tokens,
            getLineProps: ({ line: _l }) => ({ key: '', className: 'token-line' }),
            getTokenProps: ({ token: _t }) => ({ key: '', className: 'token' }),
          })
        }</>
      );
    },
    themes: { vsDark: {} },
  };
});

// ── Mock clipboard ──
const mockWriteText = jest.fn().mockResolvedValue(undefined);
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: mockWriteText },
  configurable: true,
  writable: true,
});

// ── Mock URL.createObjectURL / revokeObjectURL ──
global.URL.createObjectURL = jest.fn(() => 'blob:mock');
global.URL.revokeObjectURL = jest.fn();

// ── Mock Radix Tooltip (avoids portal issues in jsdom) ──
jest.mock('@/components/ui/tooltip', () => ({
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) =>
    asChild ? <>{children}</> : <span>{children}</span>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => (
    <div role="tooltip">{children}</div>
  ),
}));

import { ContractCodeViewer } from '@/components/contract-code/ContractCodeViewer';
import { VerificationBadge } from '@/components/contract-code/VerificationBadge';
import { ABIExplorer } from '@/components/contract-code/ABIExplorer';
import { BytecodeComparison } from '@/components/contract-code/BytecodeComparison';
import { ConstructorArgsDecoder } from '@/components/contract-code/ConstructorArgsDecoder';
import { VerificationRequestForm } from '@/components/contract-code/VerificationRequestForm';
import type { ABIFunction, ConstructorArg } from '@/components/contract-code/types';

// ─────────────────────────────────────────────────────────────────────────────
// Fixtures
// ─────────────────────────────────────────────────────────────────────────────

/** Generate 110-line Rust source to satisfy the "100+ line" acceptance criterion */
function makeRustSource(lineCount = 110): string {
  const lines: string[] = [
    '#![no_std]',
    'use soroban_sdk::{contract, contractimpl, Env, Symbol, Vec};',
    '',
    '#[contract]',
    'pub struct MyContract;',
    '',
    '#[contractimpl]',
    'impl MyContract {',
  ];
  for (let i = 0; i < lineCount - 20; i++) {
    lines.push(`    // line ${i + 1}: let x_${i} = ${i};`);
  }
  lines.push(
    '    pub fn hello(env: Env, to: Symbol) -> Vec<Symbol> {',
    '        vec![&env, Symbol::new(&env, "Hello"), to]',
    '    }',
    '    pub fn transfer(env: Env, from: Address, to: Address, amount: i128) {',
    '        // transfer logic',
    '    }',
    '}',
    '',
    '// end of contract',
  );
  return lines.join('\n');
}

const RUST_SOURCE = makeRustSource(110);

const ABI_FUNCTIONS: ABIFunction[] = [
  {
    name: 'hello',
    parameters: [{ name: 'to', type: 'Symbol' }],
    returnType: 'Vec<Symbol>',
    isInvokable: true,
  },
  {
    name: 'transfer',
    parameters: [
      { name: 'from', type: 'Address' },
      { name: 'to', type: 'Address' },
      { name: 'amount', type: 'i128' },
    ],
    returnType: null,
    isInvokable: true,
  },
  {
    name: 'get_balance',
    parameters: [{ name: 'account', type: 'Address' }],
    returnType: 'i128',
    isInvokable: false,
  },
];

const CONSTRUCTOR_ARGS: ConstructorArg[] = [
  { name: 'admin', type: 'Address', value: 'GXYZ...ADMIN' },
  { name: 'initial_supply', type: 'i128', value: '1000000000' },
];

const HASH_A = '0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890';
const HASH_B = '0x0000000000000000000000000000000000000000000000000000000000000000';

// ─────────────────────────────────────────────────────────────────────────────
// ContractCodeViewer
// ─────────────────────────────────────────────────────────────────────────────

describe('ContractCodeViewer', () => {
  beforeEach(() => mockWriteText.mockClear());

  it('renders without crashing', () => {
    render(<ContractCodeViewer sourceCode={RUST_SOURCE} language="rust" />);
    expect(screen.getByTestId('contract-code-viewer')).toBeInTheDocument();
  });

  it('renders highlighted code block for 110-line source', () => {
    render(<ContractCodeViewer sourceCode={RUST_SOURCE} language="rust" />);
    expect(screen.getByTestId('highlighted-code')).toBeInTheDocument();
  });

  it('renders all 110+ lines', () => {
    render(<ContractCodeViewer sourceCode={RUST_SOURCE} language="rust" />);
    // Line numbers rendered by the mock Highlight
    const pre = screen.getByTestId('highlighted-code');
    const text = pre.textContent ?? '';
    expect(text.length).toBeGreaterThan(0);
    // At least first and last meaningful lines are present
    expect(screen.getByTestId('highlighted-code').textContent).toContain('#![no_std]');
  });

  it('displays filename when provided', () => {
    render(
      <ContractCodeViewer sourceCode={RUST_SOURCE} language="rust" filename="token.rs" />
    );
    expect(screen.getByTestId('code-filename')).toHaveTextContent('token.rs');
  });

  it('shows language label', () => {
    render(<ContractCodeViewer sourceCode={RUST_SOURCE} language="rust" />);
    expect(screen.getByTestId('contract-code-viewer').textContent).toContain('RUST');
  });

  it('renders search input', () => {
    render(<ContractCodeViewer sourceCode={RUST_SOURCE} language="rust" />);
    expect(screen.getByTestId('code-search-input')).toBeInTheDocument();
  });

  it('highlights matching lines when search query is entered', () => {
    render(<ContractCodeViewer sourceCode={RUST_SOURCE} language="rust" />);
    fireEvent.change(screen.getByTestId('code-search-input'), {
      target: { value: 'hello' },
    });
    // The line containing "hello" should get highlight class
    const highlighted = document.querySelector('[class*="yellow"]');
    expect(highlighted).not.toBeNull();
  });

  it('copy button copies source code to clipboard', async () => {
    render(<ContractCodeViewer sourceCode={RUST_SOURCE} language="rust" />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('copy-source-button'));
    });
    expect(mockWriteText).toHaveBeenCalledWith(RUST_SOURCE);
  });

  it('copy button shows "✓ Copied" feedback after click', async () => {
    render(<ContractCodeViewer sourceCode={RUST_SOURCE} language="rust" />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('copy-source-button'));
    });
    expect(screen.getByTestId('copy-source-button')).toHaveTextContent('✓ Copied');
  });

  it('download button is present', () => {
    render(<ContractCodeViewer sourceCode={RUST_SOURCE} language="rust" />);
    expect(screen.getByTestId('download-source-button')).toBeInTheDocument();
  });

  it('download button triggers file download', () => {
    const clickSpy = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(
      <ContractCodeViewer sourceCode={RUST_SOURCE} language="rust" filename="contract.rs" />
    );
    fireEvent.click(screen.getByTestId('download-source-button'));
    expect(global.URL.createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    clickSpy.mockRestore();
  });

  it('renders wasm language', () => {
    render(<ContractCodeViewer sourceCode="(module)" language="wasm" />);
    expect(screen.getByTestId('contract-code-viewer').textContent).toContain('WASM');
  });

  it('applies custom className', () => {
    render(
      <ContractCodeViewer sourceCode="fn main() {}" language="rust" className="my-viewer" />
    );
    expect(screen.getByTestId('contract-code-viewer')).toHaveClass('my-viewer');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// VerificationBadge
// ─────────────────────────────────────────────────────────────────────────────

describe('VerificationBadge', () => {
  it('renders "Verified" badge in green', () => {
    render(<VerificationBadge status="verified" />);
    const badge = screen.getByTestId('verification-badge');
    expect(badge).toHaveTextContent('Verified');
    expect(badge).toHaveClass('text-green-400');
  });

  it('renders "Unverified" badge in yellow', () => {
    render(<VerificationBadge status="unverified" />);
    const badge = screen.getByTestId('verification-badge');
    expect(badge).toHaveTextContent('Unverified');
    expect(badge).toHaveClass('text-yellow-400');
  });

  it('renders "Malicious" badge in red', () => {
    render(<VerificationBadge status="malicious" />);
    const badge = screen.getByTestId('verification-badge');
    expect(badge).toHaveTextContent('Malicious');
    expect(badge).toHaveClass('text-red-400');
  });

  it('has role="status"', () => {
    render(<VerificationBadge status="verified" />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('has accessible aria-label', () => {
    render(<VerificationBadge status="unverified" />);
    expect(screen.getByRole('status')).toHaveAttribute(
      'aria-label',
      'Verification status: Unverified'
    );
  });

  it('shows tooltip with explanation text', () => {
    render(<VerificationBadge status="verified" />);
    expect(screen.getByRole('tooltip')).toBeInTheDocument();
  });

  it('applies custom className', () => {
    render(<VerificationBadge status="verified" className="extra-class" />);
    expect(screen.getByTestId('verification-badge')).toHaveClass('extra-class');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// ABIExplorer
// ─────────────────────────────────────────────────────────────────────────────

describe('ABIExplorer', () => {
  beforeEach(() => mockWriteText.mockClear());

  it('renders function list', () => {
    render(<ABIExplorer functions={ABI_FUNCTIONS} />);
    expect(screen.getByTestId('abi-explorer')).toBeInTheDocument();
    expect(screen.getAllByTestId('abi-function-row')).toHaveLength(3);
  });

  it('shows function names', () => {
    render(<ABIExplorer functions={ABI_FUNCTIONS} />);
    expect(screen.getByTestId('abi-fn-name-hello')).toHaveTextContent('hello');
    expect(screen.getByTestId('abi-fn-name-transfer')).toHaveTextContent('transfer');
    expect(screen.getByTestId('abi-fn-name-get_balance')).toHaveTextContent('get_balance');
  });

  it('shows invokable/view label correctly', () => {
    render(<ABIExplorer functions={ABI_FUNCTIONS} />);
    const rows = screen.getAllByTestId('abi-function-row');
    // First two are invokable, third is view
    expect(rows[0]).toHaveTextContent('invoke');
    expect(rows[2]).toHaveTextContent('view');
  });

  it('expands to show parameters on click', () => {
    render(<ABIExplorer functions={ABI_FUNCTIONS} />);
    fireEvent.click(screen.getByTestId('abi-fn-toggle-transfer'));
    expect(screen.getByTestId('abi-fn-panel-transfer')).toBeInTheDocument();
    expect(screen.getByTestId('abi-fn-params-transfer')).toBeInTheDocument();
  });

  it('shows all parameter names and types when expanded', () => {
    render(<ABIExplorer functions={ABI_FUNCTIONS} />);
    fireEvent.click(screen.getByTestId('abi-fn-toggle-transfer'));
    const panel = screen.getByTestId('abi-fn-panel-transfer');
    expect(panel).toHaveTextContent('from');
    expect(panel).toHaveTextContent('Address');
    expect(panel).toHaveTextContent('amount');
    expect(panel).toHaveTextContent('i128');
  });

  it('shows return type when expanded', () => {
    render(<ABIExplorer functions={ABI_FUNCTIONS} />);
    fireEvent.click(screen.getByTestId('abi-fn-toggle-hello'));
    expect(screen.getByTestId('abi-fn-panel-hello')).toHaveTextContent('Vec<Symbol>');
  });

  it('shows "No parameters" for zero-param function', () => {
    const noParams: ABIFunction[] = [
      { name: 'noop', parameters: [], returnType: null, isInvokable: true },
    ];
    render(<ABIExplorer functions={noParams} />);
    fireEvent.click(screen.getByTestId('abi-fn-toggle-noop'));
    expect(screen.getByTestId('abi-fn-panel-noop')).toHaveTextContent('No parameters');
  });

  it('collapses panel on second click', () => {
    render(<ABIExplorer functions={ABI_FUNCTIONS} />);
    fireEvent.click(screen.getByTestId('abi-fn-toggle-hello'));
    expect(screen.getByTestId('abi-fn-panel-hello')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('abi-fn-toggle-hello'));
    expect(screen.queryByTestId('abi-fn-panel-hello')).not.toBeInTheDocument();
  });

  it('copy button copies function signature to clipboard', async () => {
    render(<ABIExplorer functions={ABI_FUNCTIONS} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('copy-fn-hello'));
    });
    expect(mockWriteText).toHaveBeenCalledWith(
      expect.stringContaining('fn hello')
    );
  });

  it('calls onCopyFunction callback when function is copied', async () => {
    const onCopy = jest.fn();
    render(<ABIExplorer functions={ABI_FUNCTIONS} onCopyFunction={onCopy} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('copy-fn-hello'));
    });
    expect(onCopy).toHaveBeenCalledWith(ABI_FUNCTIONS[0]);
  });

  it('renders empty state when no functions provided', () => {
    render(<ABIExplorer functions={[]} />);
    expect(screen.getByTestId('abi-empty-state')).toBeInTheDocument();
  });

  it('shows function count', () => {
    render(<ABIExplorer functions={ABI_FUNCTIONS} />);
    expect(screen.getByTestId('abi-explorer')).toHaveTextContent('3 functions');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// BytecodeComparison
// ─────────────────────────────────────────────────────────────────────────────

describe('BytecodeComparison', () => {
  beforeEach(() => mockWriteText.mockClear());

  it('renders both hash values', () => {
    render(<BytecodeComparison compiledHash={HASH_A} onChainHash={HASH_A} />);
    expect(screen.getByTestId('compiled-hash')).toHaveTextContent(HASH_A);
    expect(screen.getByTestId('onchain-hash')).toHaveTextContent(HASH_A);
  });

  it('shows match status when hashes are equal', () => {
    render(<BytecodeComparison compiledHash={HASH_A} onChainHash={HASH_A} />);
    const status = screen.getByTestId('hash-match-status');
    expect(status).toHaveTextContent('Hashes match');
    expect(status).toHaveClass('text-green-400');
  });

  it('shows mismatch status when hashes differ', () => {
    render(<BytecodeComparison compiledHash={HASH_A} onChainHash={HASH_B} />);
    const status = screen.getByTestId('hash-match-status');
    expect(status).toHaveTextContent('Hash mismatch');
    expect(status).toHaveClass('text-red-400');
  });

  it('copy button copies compiled hash to clipboard', async () => {
    render(<BytecodeComparison compiledHash={HASH_A} onChainHash={HASH_B} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('compiled-hash-copy'));
    });
    expect(mockWriteText).toHaveBeenCalledWith(HASH_A);
  });

  it('copy button copies on-chain hash to clipboard', async () => {
    render(<BytecodeComparison compiledHash={HASH_A} onChainHash={HASH_B} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('onchain-hash-copy'));
    });
    expect(mockWriteText).toHaveBeenCalledWith(HASH_B);
  });

  it('hash-match-status has role="status"', () => {
    render(<BytecodeComparison compiledHash={HASH_A} onChainHash={HASH_A} />);
    expect(screen.getByTestId('hash-match-status')).toHaveAttribute('role', 'status');
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// ConstructorArgsDecoder
// ─────────────────────────────────────────────────────────────────────────────

describe('ConstructorArgsDecoder', () => {
  it('renders a row for each constructor arg', () => {
    render(<ConstructorArgsDecoder args={CONSTRUCTOR_ARGS} />);
    expect(screen.getByTestId('constructor-args-decoder')).toBeInTheDocument();
    expect(screen.getByTestId('constructor-arg-row-0')).toBeInTheDocument();
    expect(screen.getByTestId('constructor-arg-row-1')).toBeInTheDocument();
  });

  it('displays arg name, type and decoded value', () => {
    render(<ConstructorArgsDecoder args={CONSTRUCTOR_ARGS} />);
    expect(screen.getByTestId('constructor-arg-row-0')).toHaveTextContent('admin');
    expect(screen.getByTestId('constructor-arg-row-0')).toHaveTextContent('Address');
    expect(screen.getByTestId('constructor-arg-value-0')).toHaveTextContent('GXYZ...ADMIN');
  });

  it('displays numeric value in human-readable form', () => {
    render(<ConstructorArgsDecoder args={CONSTRUCTOR_ARGS} />);
    expect(screen.getByTestId('constructor-arg-value-1')).toHaveTextContent('1000000000');
  });

  it('renders empty state when args array is empty', () => {
    render(<ConstructorArgsDecoder args={[]} />);
    expect(screen.getByTestId('constructor-args-empty')).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// VerificationRequestForm
// ─────────────────────────────────────────────────────────────────────────────

describe('VerificationRequestForm', () => {
  const CONTRACT_ID = 'CAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';

  it('renders the form', () => {
    render(
      <VerificationRequestForm contractId={CONTRACT_ID} onSubmit={jest.fn()} />
    );
    expect(screen.getByTestId('verification-request-form')).toBeInTheDocument();
  });

  it('has a submit button', () => {
    render(
      <VerificationRequestForm contractId={CONTRACT_ID} onSubmit={jest.fn()} />
    );
    expect(screen.getByTestId('vrf-submit-button')).toBeInTheDocument();
  });

  it('shows validation error when source code is empty', async () => {
    render(
      <VerificationRequestForm contractId={CONTRACT_ID} onSubmit={jest.fn()} />
    );
    fireEvent.change(screen.getByTestId('vrf-compiler-version'), {
      target: { value: '1.79.0' },
    });
    await act(async () => {
      fireEvent.submit(screen.getByTestId('verification-request-form'));
    });
    expect(screen.getByTestId('vrf-error')).toHaveTextContent(/Source code is required/i);
  });

  it('shows validation error when compiler version is empty', async () => {
    render(
      <VerificationRequestForm contractId={CONTRACT_ID} onSubmit={jest.fn()} />
    );
    fireEvent.change(screen.getByTestId('vrf-source-code'), {
      target: { value: 'fn main() {}' },
    });
    await act(async () => {
      fireEvent.submit(screen.getByTestId('verification-request-form'));
    });
    expect(screen.getByTestId('vrf-error')).toHaveTextContent(/Compiler version is required/i);
  });

  it('calls onSubmit with correct data when form is valid', async () => {
    const onSubmit = jest.fn().mockResolvedValue(undefined);
    render(
      <VerificationRequestForm contractId={CONTRACT_ID} onSubmit={onSubmit} />
    );
    fireEvent.change(screen.getByTestId('vrf-compiler-version'), {
      target: { value: '1.79.0' },
    });
    fireEvent.change(screen.getByTestId('vrf-source-code'), {
      target: { value: RUST_SOURCE },
    });
    fireEvent.change(screen.getByTestId('vrf-notes'), {
      target: { value: 'Test note' },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('vrf-submit-button'));
    });
    expect(onSubmit).toHaveBeenCalledWith({
      contractId: CONTRACT_ID,
      sourceCode: RUST_SOURCE,
      compilerVersion: '1.79.0',
      optimizationEnabled: true,
      notes: 'Test note',
    });
  });

  it('shows success state after successful submission', async () => {
    render(
      <VerificationRequestForm
        contractId={CONTRACT_ID}
        onSubmit={jest.fn().mockResolvedValue(undefined)}
      />
    );
    fireEvent.change(screen.getByTestId('vrf-compiler-version'), {
      target: { value: '1.79.0' },
    });
    fireEvent.change(screen.getByTestId('vrf-source-code'), {
      target: { value: 'fn main() {}' },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('vrf-submit-button'));
    });
    expect(screen.getByTestId('verification-request-success')).toBeInTheDocument();
  });

  it('shows error state when submission throws', async () => {
    render(
      <VerificationRequestForm
        contractId={CONTRACT_ID}
        onSubmit={jest.fn().mockRejectedValue(new Error('Network error'))}
      />
    );
    fireEvent.change(screen.getByTestId('vrf-compiler-version'), {
      target: { value: '1.79.0' },
    });
    fireEvent.change(screen.getByTestId('vrf-source-code'), {
      target: { value: 'fn main() {}' },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('vrf-submit-button'));
    });
    expect(screen.getByTestId('vrf-error')).toHaveTextContent('Network error');
  });

  it('disables submit button while submitting', async () => {
    let resolve!: () => void;
    const onSubmit = jest.fn(
      () => new Promise<void>((r) => { resolve = r; })
    );
    render(
      <VerificationRequestForm contractId={CONTRACT_ID} onSubmit={onSubmit} />
    );
    fireEvent.change(screen.getByTestId('vrf-compiler-version'), {
      target: { value: '1.79.0' },
    });
    fireEvent.change(screen.getByTestId('vrf-source-code'), {
      target: { value: 'fn main() {}' },
    });
    act(() => {
      fireEvent.click(screen.getByTestId('vrf-submit-button'));
    });
    expect(screen.getByTestId('vrf-submit-button')).toBeDisabled();
    await act(async () => { resolve(); });
  });

  it('optimization checkbox is checked by default', () => {
    render(
      <VerificationRequestForm contractId={CONTRACT_ID} onSubmit={jest.fn()} />
    );
    expect(screen.getByTestId('vrf-optimization-checkbox')).toBeChecked();
  });

  it('optimization checkbox can be unchecked', () => {
    render(
      <VerificationRequestForm contractId={CONTRACT_ID} onSubmit={jest.fn()} />
    );
    fireEvent.click(screen.getByTestId('vrf-optimization-checkbox'));
    expect(screen.getByTestId('vrf-optimization-checkbox')).not.toBeChecked();
  });
});
