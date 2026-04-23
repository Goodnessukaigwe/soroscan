import { SearchCriteria } from '../components/AdvancedSearchForm';
import { SavedSearch } from '../components/SavedSearchList';

/**
 * Generate a shareable URL for a search
 */
export function generateShareableUrl(criteria: SearchCriteria, baseUrl?: string): string {
  const criteriaJson = JSON.stringify(criteria);
  const encodedCriteria = encodeURIComponent(criteriaJson);
  const base = baseUrl || (typeof window !== 'undefined' ? window.location.origin : '');
  return `${base}/search?criteria=${encodedCriteria}`;
}

/**
 * Parse search criteria from URL
 */
export function parseCriteriaFromUrl(url: string): SearchCriteria | null {
  try {
    const urlObj = new URL(url);
    const criteriaParam = urlObj.searchParams.get('criteria');
    if (!criteriaParam) return null;
    
    return JSON.parse(decodeURIComponent(criteriaParam));
  } catch (e) {
    console.error('Failed to parse criteria from URL', e);
    return null;
  }
}

/**
 * Export search as JSON file
 */
export function exportSearchAsJson(search: SavedSearch): void {
  const dataStr = JSON.stringify(search, null, 2);
  const dataBlob = new Blob([dataStr], { type: 'application/json' });
  const url = URL.createObjectURL(dataBlob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `search-${search.name.replace(/\s+/g, '-').toLowerCase()}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Export search as CSV file
 */
export function exportSearchAsCsv(search: SavedSearch): void {
  const criteria = search.criteria;
  const rows = [
    ['Field', 'Value'],
    ['Name', search.name],
    ['Created', search.createdAt],
    ['Contract', criteria.contract || ''],
    ['Event Type', criteria.eventType || ''],
    ['Date From', criteria.dateFrom || ''],
    ['Date To', criteria.dateTo || ''],
    ['Amount Min', criteria.amountMin?.toString() || ''],
    ['Amount Max', criteria.amountMax?.toString() || ''],
    ['Status', criteria.status || ''],
  ];

  const csvContent = rows.map(row => row.map(cell => `"${cell}"`).join(',')).join('\n');
  const dataBlob = new Blob([csvContent], { type: 'text/csv' });
  const url = URL.createObjectURL(dataBlob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `search-${search.name.replace(/\s+/g, '-').toLowerCase()}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Copy text to clipboard
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (e) {
    console.error('Failed to copy to clipboard', e);
    return false;
  }
}

/**
 * Format search criteria as human-readable text
 */
export function formatCriteriaAsText(criteria: SearchCriteria): string {
  const parts: string[] = [];
  
  if (criteria.contract) {
    parts.push(`Contract: ${criteria.contract}`);
  }
  if (criteria.eventType) {
    parts.push(`Event Type: ${criteria.eventType}`);
  }
  if (criteria.dateFrom || criteria.dateTo) {
    const from = criteria.dateFrom || 'any';
    const to = criteria.dateTo || 'any';
    parts.push(`Date Range: ${from} to ${to}`);
  }
  if (criteria.amountMin !== undefined || criteria.amountMax !== undefined) {
    const min = criteria.amountMin ?? 0;
    const max = criteria.amountMax ?? '∞';
    parts.push(`Amount Range: ${min} - ${max} XLM`);
  }
  if (criteria.status) {
    parts.push(`Status: ${criteria.status}`);
  }

  return parts.length > 0 ? parts.join(' | ') : 'No filters applied';
}
