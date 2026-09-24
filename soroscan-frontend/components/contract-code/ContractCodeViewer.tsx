'use client';

import * as React from 'react';
import { Highlight, themes } from 'prism-react-renderer';
import { cn } from '@/lib/utils';
import type { CodeLanguage } from './types';

export interface ContractCodeViewerProps {
  sourceCode: string;
  language: CodeLanguage;
  filename?: string;
  className?: string;
}

/** Map our language names to prism-react-renderer token grammar keys */
const PRISM_LANGUAGE: Record<CodeLanguage, string> = {
  rust: 'rust',
  wasm: 'wasm',
};

export function ContractCodeViewer({
  sourceCode,
  language,
  filename,
  className,
}: ContractCodeViewerProps) {
  const [searchQuery, setSearchQuery] = React.useState('');
  const [copied, setCopied] = React.useState(false);
  const searchRef = React.useRef<HTMLInputElement>(null);

  /* ── Cmd/Ctrl+F opens in-page search ── */
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'f') {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  /* ── Copy source ── */
  const handleCopy = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(sourceCode);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = sourceCode;
      ta.style.cssText = 'position:fixed;opacity:0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [sourceCode]);

  /* ── Download source ── */
  const handleDownload = React.useCallback(() => {
    const ext = language === 'rust' ? 'rs' : 'wat';
    const name = filename ?? `contract.${ext}`;
    const blob = new Blob([sourceCode], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  }, [sourceCode, language, filename]);

  /* ── Highlight search matches ── */
  const highlightLine = React.useCallback(
    (line: string) => {
      if (!searchQuery.trim()) return false;
      return line.toLowerCase().includes(searchQuery.toLowerCase());
    },
    [searchQuery]
  );

  const lineCount = sourceCode.split('\n').length;

  return (
    <div
      className={cn('flex flex-col rounded-lg border border-green-800 bg-gray-950 overflow-hidden', className)}
      data-testid="contract-code-viewer"
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 px-4 py-2 border-b border-green-800 bg-gray-900">
        <div className="flex items-center gap-3">
          {filename && (
            <span className="text-xs font-mono text-green-400" data-testid="code-filename">
              {filename}
            </span>
          )}
          <span className="text-xs text-gray-500 font-mono">
            {lineCount} lines · {language.toUpperCase()}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* In-page search */}
          <div className="relative">
            <input
              ref={searchRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search… (⌘F)"
              aria-label="Search source code"
              data-testid="code-search-input"
              className="w-40 sm:w-56 h-7 px-2 text-xs font-mono bg-gray-800 border border-green-800 rounded text-green-300 placeholder-gray-600 focus:outline-none focus:border-green-500"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                aria-label="Clear search"
                className="absolute right-1.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs"
              >
                ✕
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={handleCopy}
            aria-label={copied ? 'Copied' : 'Copy source code'}
            data-testid="copy-source-button"
            className="px-2.5 py-1 text-xs font-mono rounded border border-green-800 bg-gray-800 text-green-400 hover:bg-green-900/30 transition-colors"
          >
            {copied ? '✓ Copied' : 'Copy'}
          </button>

          <button
            type="button"
            onClick={handleDownload}
            aria-label="Download source file"
            data-testid="download-source-button"
            className="px-2.5 py-1 text-xs font-mono rounded border border-green-800 bg-gray-800 text-green-400 hover:bg-green-900/30 transition-colors"
          >
            ↓ Download
          </button>
        </div>
      </div>

      {/* Code area */}
      <div
        className="overflow-auto max-h-[600px]"
        data-testid="code-scroll-container"
      >
        <Highlight
          theme={themes.vsDark}
          code={sourceCode}
          language={PRISM_LANGUAGE[language]}
        >
          {({ className: hlClass, style, tokens, getLineProps, getTokenProps }) => (
            <pre
              className={cn(hlClass, 'text-xs leading-relaxed p-4 m-0 bg-transparent')}
              style={{ ...style, background: 'transparent' }}
              data-testid="highlighted-code"
            >
              {tokens.map((line, lineIdx) => {
                const lineText = line.map((t) => t.content).join('');
                const isMatch = highlightLine(lineText);
                const lineNumber = lineIdx + 1;
                const { key: lineKey, ...lineProps } = getLineProps({ line });
                return (
                  <div
                    key={lineIdx}
                    {...lineProps}
                    data-line={lineNumber}
                    className={cn(
                      'flex',
                      isMatch && 'bg-yellow-500/10 outline outline-1 outline-yellow-600/40 -outline-offset-1'
                    )}
                  >
                    <span
                      className="select-none w-10 shrink-0 pr-4 text-right text-gray-600 font-mono"
                      aria-hidden="true"
                    >
                      {lineNumber}
                    </span>
                    <span className="flex-1">
                      {line.map((token, tokenIdx) => {
                        const { key: tokenKey, ...tokenProps } = getTokenProps({ token });
                        return (
                          <span key={tokenIdx} {...tokenProps}>{token.content}</span>
                        );
                      })}
                    </span>
                  </div>
                );
              })}
            </pre>
          )}
        </Highlight>
      </div>
    </div>
  );
}
