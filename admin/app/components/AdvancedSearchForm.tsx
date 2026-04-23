'use client';

import React, { useState } from 'react';

export interface SearchCriteria {
  contract?: string;
  eventType?: string;
  dateFrom?: string;
  dateTo?: string;
  amountMin?: number;
  amountMax?: number;
  status?: string;
}

export interface AdvancedSearchFormProps {
  onSearch: (criteria: SearchCriteria) => void;
  onSave: (criteria: SearchCriteria, name: string) => void;
  initialCriteria?: SearchCriteria;
  className?: string;
}

export function AdvancedSearchForm({
  onSearch,
  onSave,
  initialCriteria = {},
  className = '',
}: AdvancedSearchFormProps) {
  const [criteria, setCriteria] = useState<SearchCriteria>(initialCriteria);
  const [searchName, setSearchName] = useState('');
  const [showSaveDialog, setShowSaveDialog] = useState(false);

  const handleInputChange = (field: keyof SearchCriteria, value: string | number) => {
    setCriteria((prev) => ({ ...prev, [field]: value }));
  };

  const handleSearch = () => {
    onSearch(criteria);
  };

  const handleSave = () => {
    if (searchName.trim()) {
      onSave(criteria, searchName);
      setSearchName('');
      setShowSaveDialog(false);
    }
  };

  const handleReset = () => {
    setCriteria({});
  };

  return (
    <div className={`bg-zinc-900 border border-zinc-800 rounded-lg p-6 ${className}`}>
      <h2 className="text-lg font-mono text-zinc-100 uppercase tracking-wider mb-4">
        Advanced Search
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {/* Contract Address */}
        <div>
          <label className="block text-xs font-mono text-zinc-400 mb-2 uppercase">
            Contract Address
          </label>
          <input
            type="text"
            value={criteria.contract || ''}
            onChange={(e) => handleInputChange('contract', e.target.value)}
            placeholder="Enter contract address"
            className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-sm font-mono text-zinc-100 focus:outline-none focus:border-zinc-500"
          />
        </div>

        {/* Event Type */}
        <div>
          <label className="block text-xs font-mono text-zinc-400 mb-2 uppercase">
            Event Type
          </label>
          <select
            value={criteria.eventType || ''}
            onChange={(e) => handleInputChange('eventType', e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-sm font-mono text-zinc-100 focus:outline-none focus:border-zinc-500"
          >
            <option value="">All Types</option>
            <option value="transfer">Transfer</option>
            <option value="mint">Mint</option>
            <option value="burn">Burn</option>
            <option value="approve">Approve</option>
          </select>
        </div>

        {/* Date From */}
        <div>
          <label className="block text-xs font-mono text-zinc-400 mb-2 uppercase">
            Date From
          </label>
          <input
            type="date"
            value={criteria.dateFrom || ''}
            onChange={(e) => handleInputChange('dateFrom', e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-sm font-mono text-zinc-100 focus:outline-none focus:border-zinc-500"
          />
        </div>

        {/* Date To */}
        <div>
          <label className="block text-xs font-mono text-zinc-400 mb-2 uppercase">
            Date To
          </label>
          <input
            type="date"
            value={criteria.dateTo || ''}
            onChange={(e) => handleInputChange('dateTo', e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-sm font-mono text-zinc-100 focus:outline-none focus:border-zinc-500"
          />
        </div>

        {/* Amount Min */}
        <div>
          <label className="block text-xs font-mono text-zinc-400 mb-2 uppercase">
            Amount Min (XLM)
          </label>
          <input
            type="number"
            value={criteria.amountMin || ''}
            onChange={(e) => handleInputChange('amountMin', parseFloat(e.target.value))}
            placeholder="0"
            className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-sm font-mono text-zinc-100 focus:outline-none focus:border-zinc-500"
          />
        </div>

        {/* Amount Max */}
        <div>
          <label className="block text-xs font-mono text-zinc-400 mb-2 uppercase">
            Amount Max (XLM)
          </label>
          <input
            type="number"
            value={criteria.amountMax || ''}
            onChange={(e) => handleInputChange('amountMax', parseFloat(e.target.value))}
            placeholder="∞"
            className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-sm font-mono text-zinc-100 focus:outline-none focus:border-zinc-500"
          />
        </div>

        {/* Status */}
        <div className="md:col-span-2">
          <label className="block text-xs font-mono text-zinc-400 mb-2 uppercase">
            Status
          </label>
          <select
            value={criteria.status || ''}
            onChange={(e) => handleInputChange('status', e.target.value)}
            className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-sm font-mono text-zinc-100 focus:outline-none focus:border-zinc-500"
          >
            <option value="">All Statuses</option>
            <option value="success">Success</option>
            <option value="failed">Failed</option>
            <option value="pending">Pending</option>
          </select>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={handleSearch}
          className="px-4 py-2 bg-green-600 hover:bg-green-700 text-zinc-950 font-mono text-sm rounded transition-colors"
        >
          ▶ SEARCH
        </button>
        <button
          onClick={() => setShowSaveDialog(true)}
          className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-zinc-100 font-mono text-sm rounded transition-colors"
        >
          ⭐ SAVE SEARCH
        </button>
        <button
          onClick={handleReset}
          className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 font-mono text-sm rounded transition-colors"
        >
          ✕ RESET
        </button>
      </div>

      {/* Save Dialog */}
      {showSaveDialog && (
        <div className="mt-4 p-4 bg-zinc-950 border border-zinc-700 rounded">
          <label className="block text-xs font-mono text-zinc-400 mb-2 uppercase">
            Search Name
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={searchName}
              onChange={(e) => setSearchName(e.target.value)}
              placeholder="e.g., Large transfers last 7 days"
              className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm font-mono text-zinc-100 focus:outline-none focus:border-zinc-500"
              autoFocus
            />
            <button
              onClick={handleSave}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-zinc-950 font-mono text-sm rounded transition-colors"
            >
              SAVE
            </button>
            <button
              onClick={() => setShowSaveDialog(false)}
              className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 font-mono text-sm rounded transition-colors"
            >
              CANCEL
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
