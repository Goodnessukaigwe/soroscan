'use client';

import React from 'react';
import { SearchCriteria } from './AdvancedSearchForm';

export interface SavedSearch {
  id: string;
  name: string;
  criteria: SearchCriteria;
  createdAt: string;
}

export interface SavedSearchListProps {
  searches: SavedSearch[];
  onLoad: (search: SavedSearch) => void;
  onDelete: (id: string) => void;
  onShare: (search: SavedSearch) => void;
  onExport: (search: SavedSearch) => void;
  className?: string;
}

export function SavedSearchList({
  searches,
  onLoad,
  onDelete,
  onShare,
  onExport,
  className = '',
}: SavedSearchListProps) {
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const getCriteriaPreview = (criteria: SearchCriteria): string => {
    const parts: string[] = [];
    if (criteria.contract) parts.push(`Contract: ${criteria.contract.slice(0, 8)}...`);
    if (criteria.eventType) parts.push(`Type: ${criteria.eventType}`);
    if (criteria.dateFrom || criteria.dateTo) {
      parts.push(`Date: ${criteria.dateFrom || '∞'} - ${criteria.dateTo || '∞'}`);
    }
    if (criteria.amountMin || criteria.amountMax) {
      parts.push(`Amount: ${criteria.amountMin || 0} - ${criteria.amountMax || '∞'} XLM`);
    }
    if (criteria.status) parts.push(`Status: ${criteria.status}`);
    return parts.join(' | ') || 'No filters';
  };

  if (searches.length === 0) {
    return (
      <div className={`bg-zinc-900 border border-zinc-800 rounded-lg p-6 ${className}`}>
        <h3 className="text-sm font-mono text-zinc-100 uppercase tracking-wider mb-4">
          Saved Searches
        </h3>
        <p className="text-xs font-mono text-zinc-500 text-center py-8">
          No saved searches yet. Create one from the search form.
        </p>
      </div>
    );
  }

  return (
    <div className={`bg-zinc-900 border border-zinc-800 rounded-lg p-6 ${className}`}>
      <h3 className="text-sm font-mono text-zinc-100 uppercase tracking-wider mb-4">
        Saved Searches ({searches.length})
      </h3>

      <div className="space-y-3">
        {searches.map((search) => (
          <div
            key={search.id}
            className="bg-zinc-950 border border-zinc-800 rounded p-4 hover:border-zinc-700 transition-colors"
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex-1">
                <h4 className="text-sm font-mono text-zinc-100 mb-1">{search.name}</h4>
                <p className="text-xs font-mono text-zinc-500">
                  {formatDate(search.createdAt)}
                </p>
              </div>
              <button
                onClick={() => onDelete(search.id)}
                className="text-zinc-500 hover:text-red-500 transition-colors ml-2"
                title="Delete search"
              >
                <span className="text-xs">✕</span>
              </button>
            </div>

            <p className="text-xs font-mono text-zinc-400 mb-3 break-all">
              {getCriteriaPreview(search.criteria)}
            </p>

            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => onLoad(search)}
                className="px-3 py-1 bg-green-600 hover:bg-green-700 text-zinc-950 font-mono text-xs rounded transition-colors"
              >
                ▶ LOAD
              </button>
              <button
                onClick={() => onShare(search)}
                className="px-3 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-100 font-mono text-xs rounded transition-colors"
              >
                🔗 SHARE
              </button>
              <button
                onClick={() => onExport(search)}
                className="px-3 py-1 bg-zinc-700 hover:bg-zinc-600 text-zinc-100 font-mono text-xs rounded transition-colors"
              >
                ↓ EXPORT
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
