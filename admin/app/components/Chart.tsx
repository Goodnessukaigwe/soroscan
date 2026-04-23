'use client';

import React from 'react';

export interface ChartProps {
  title?: string;
  description?: string;
  className?: string;
  children: React.ReactNode;
  onExport?: () => void;
}

export function Chart({ title, description, className = '', children, onExport }: ChartProps) {
  return (
    <div className={`bg-zinc-900 border border-zinc-800 rounded-lg p-4 ${className}`}>
      {(title || description || onExport) && (
        <div className="flex items-start justify-between mb-4">
          <div>
            {title && (
              <h3 className="text-sm font-mono text-zinc-100 uppercase tracking-wider">
                {title}
              </h3>
            )}
            {description && (
              <p className="text-xs text-zinc-500 mt-1 font-mono">{description}</p>
            )}
          </div>
          {onExport && (
            <button
              onClick={onExport}
              className="text-xs font-mono text-zinc-400 hover:text-zinc-100 transition-colors px-2 py-1 border border-zinc-700 rounded hover:border-zinc-500"
              title="Export as image"
            >
              ↓ EXPORT
            </button>
          )}
        </div>
      )}
      <div className="w-full">{children}</div>
    </div>
  );
}
