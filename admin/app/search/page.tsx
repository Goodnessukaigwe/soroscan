'use client';

import React, { useState, useEffect } from 'react';
import { AdvancedSearchForm, SearchCriteria } from '../components/AdvancedSearchForm';
import { SavedSearchList, SavedSearch } from '../components/SavedSearchList';
import { SearchHistory, SearchHistoryItem } from '../components/SearchHistory';

export default function SearchPage() {
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);
  const [searchHistory, setSearchHistory] = useState<SearchHistoryItem[]>([]);
  const [currentCriteria, setCurrentCriteria] = useState<SearchCriteria>({});
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [shareUrl, setShareUrl] = useState<string>('');

  // Load from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('savedSearches');
    const history = localStorage.getItem('searchHistory');
    
    if (saved) setSavedSearches(JSON.parse(saved));
    if (history) setSearchHistory(JSON.parse(history));

    // Load from URL if present
    const params = new URLSearchParams(window.location.search);
    const criteriaParam = params.get('criteria');
    if (criteriaParam) {
      try {
        const criteria = JSON.parse(decodeURIComponent(criteriaParam));
        setCurrentCriteria(criteria);
      } catch (e) {
        console.error('Failed to parse criteria from URL', e);
      }
    }
  }, []);

  const handleSearch = (criteria: SearchCriteria) => {
    setCurrentCriteria(criteria);
    
    // Simulate search results
    const mockResults = [
      { id: '1', event: 'transfer', amount: 1500, timestamp: new Date().toISOString() },
      { id: '2', event: 'transfer', amount: 2000, timestamp: new Date().toISOString() },
    ];
    setSearchResults(mockResults);

    // Add to history
    const historyItem: SearchHistoryItem = {
      id: Date.now().toString(),
      criteria,
      timestamp: new Date().toISOString(),
      resultCount: mockResults.length,
    };

    const newHistory = [historyItem, ...searchHistory].slice(0, 20);
    setSearchHistory(newHistory);
    localStorage.setItem('searchHistory', JSON.stringify(newHistory));
  };

  const handleSaveSearch = (criteria: SearchCriteria, name: string) => {
    const newSearch: SavedSearch = {
      id: Date.now().toString(),
      name,
      criteria,
      createdAt: new Date().toISOString(),
    };

    const updated = [...savedSearches, newSearch];
    setSavedSearches(updated);
    localStorage.setItem('savedSearches', JSON.stringify(updated));
  };

  const handleLoadSavedSearch = (search: SavedSearch) => {
    setCurrentCriteria(search.criteria);
    handleSearch(search.criteria);
  };

  const handleDeleteSavedSearch = (id: string) => {
    const updated = savedSearches.filter((s) => s.id !== id);
    setSavedSearches(updated);
    localStorage.setItem('savedSearches', JSON.stringify(updated));
  };

  const handleShareSearch = (search: SavedSearch) => {
    const criteriaJson = JSON.stringify(search.criteria);
    const encodedCriteria = encodeURIComponent(criteriaJson);
    const url = `${window.location.origin}${window.location.pathname}?criteria=${encodedCriteria}`;
    
    navigator.clipboard.writeText(url);
    setShareUrl(url);
    
    setTimeout(() => setShareUrl(''), 3000);
  };

  const handleExportSearch = (search: SavedSearch) => {
    const dataStr = JSON.stringify(search, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `search-${search.name.replace(/\s+/g, '-').toLowerCase()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleLoadHistoryItem = (item: SearchHistoryItem) => {
    setCurrentCriteria(item.criteria);
    handleSearch(item.criteria);
  };

  const handleClearHistory = () => {
    setSearchHistory([]);
    localStorage.removeItem('searchHistory');
  };

  return (
    <div className="min-h-screen bg-zinc-950 p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-mono text-zinc-100 uppercase tracking-wider mb-2">
          Advanced Search
        </h1>
        <p className="text-sm font-mono text-zinc-500">
          Search, save, and share your queries
        </p>
      </div>

      {/* Share URL Notification */}
      {shareUrl && (
        <div className="mb-6 bg-green-900 border border-green-700 rounded-lg p-4">
          <p className="text-sm font-mono text-green-100 mb-2">
            ✓ Link copied to clipboard!
          </p>
          <p className="text-xs font-mono text-green-300 break-all">{shareUrl}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Search Area */}
        <div className="lg:col-span-2 space-y-6">
          <AdvancedSearchForm
            onSearch={handleSearch}
            onSave={handleSaveSearch}
            initialCriteria={currentCriteria}
          />

          {/* Search Results */}
          {searchResults.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
              <h3 className="text-sm font-mono text-zinc-100 uppercase tracking-wider mb-4">
                Search Results ({searchResults.length})
              </h3>
              <div className="space-y-2">
                {searchResults.map((result) => (
                  <div
                    key={result.id}
                    className="bg-zinc-950 border border-zinc-800 rounded p-3"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-zinc-300">
                        {result.event.toUpperCase()}
                      </span>
                      <span className="text-xs font-mono text-green-500">
                        {result.amount} XLM
                      </span>
                    </div>
                    <p className="text-xs font-mono text-zinc-600 mt-1">
                      {new Date(result.timestamp).toLocaleString()}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          <SavedSearchList
            searches={savedSearches}
            onLoad={handleLoadSavedSearch}
            onDelete={handleDeleteSavedSearch}
            onShare={handleShareSearch}
            onExport={handleExportSearch}
          />

          <SearchHistory
            history={searchHistory}
            onLoad={handleLoadHistoryItem}
            onClear={handleClearHistory}
          />
        </div>
      </div>
    </div>
  );
}
