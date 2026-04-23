'use client';

import React from 'react';
import { SearchCriteria } from './AdvancedSearchForm';

export interface SearchHistoryItem {
  id: string;
  criteria: SearchCriteria;
  timestamp: string;
  resultCount?: number;
}

export interface SearchHistoryProps {
  history: SearchHistoryItem[];
  onLoad: (item: SearchHistoryItem) => void;
  onClear: () => void;
  className?: string;
}

export function SearchHistory({
  history,
  onLoad,
  onClear,
  className = '',
}: SearchHistoryProps) {
  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const getCriteriaText = (criteria: SearchCriteria): string => {
    const parts: string[] = [];
    if (criteria.eventType) parts.push(criteria.eventType);
    if (criteria.amountMin) parts.push(`>${criteria.amountMin} XLM`);
    if (criteria.dateFrom) parts.push(`from ${criteria.dateFrom}`);
    if (criteria.status) parts.push(criteria.status);
    
    return parts.length > 0 ? parts.join(', ') : 'All events';
  };

  if (history.length === 0) {
    return (
      <div className={`bg-zinc-900 border border-zinc-800 rounded-lg p-6 ${className}`}>
        <h3 className="text-sm font-mono text-zinc-100 uppercase tracking-wider mb-4">
          Search History
        </h3>
        <p className="text-xs font-mono text-zinc-500 text-center py-8">
          No search history yet. Your searches will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className={`bg-zinc-900 border border-zinc-800 rounded-lg p-6 ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-mono text-zinc-100 uppercase tracking-wider">
          Search History ({history.length})
        </h3>
        <button
          onClick={onClear}
          className="text-xs font-mono text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          CLEAR ALL
        </button>
      </div>

      <div className="space-y-2 max-h-96 overflow-y-auto">
        {history.map((item) => (
          <button
            key={item.id}
            onClick={() => onLoad(item)}
            className="w-full text-left bg-zinc-950 border border-zinc-800 rounded p-3 hover:border-zinc-700 hover:bg-zinc-900 transition-colors"
          >
            <div className="flex items-start justify-between mb-1">
              <p className="text-xs font-mono text-zinc-300 flex-1 break-all">
                {getCriteriaText(item.criteria)}
              </p>
              <span className="text-xs font-mono text-zinc-500 ml-2 whitespace-nowrap">
                {formatTime(item.timestamp)}
              </span>
            </div>
            {item.resultCount !== undefined && (
              <p className="text-xs font-mono text-zinc-600">
                {item.resultCount} results
              </p>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
