# Advanced Search & Saved Searches Feature

## Overview
Advanced search functionality with saved searches, search history, and shareable URLs for the SoroScan admin dashboard.

## Components Created

### 1. AdvancedSearchForm.tsx
Multi-criteria search form with:
- Contract address filter
- Event type selection
- Date range (from/to)
- Amount range (min/max XLM)
- Status filter
- Save search functionality
- Reset button

### 2. SavedSearchList.tsx
Displays saved searches with:
- Search name and creation date
- Criteria preview
- Load, Share, Export, and Delete actions
- Empty state message

### 3. SearchHistory.tsx
Shows recent searches (last 20) with:
- Criteria summary
- Relative timestamps
- Result count
- One-click reload
- Clear all functionality

### 4. Search Page (app/search/page.tsx)
Main search interface combining all components with:
- Advanced search form
- Search results display
- Saved searches sidebar
- Search history sidebar
- URL-based search loading

## Features Implemented

### ✅ Advanced Search Form
- Multiple filter criteria
- Intuitive form layout
- Real-time validation
- Reset functionality

### ✅ Save Search
- Name your searches
- Store in localStorage
- Persistent across sessions
- Quick save dialog

### ✅ Load Saved Searches
- One-click load
- Populates form automatically
- Executes search immediately

### ✅ Search History
- Automatic tracking (last 20)
- Relative timestamps
- Result count display
- Clear all option

### ✅ Shareable URLs
- Generate shareable links
- Criteria encoded in URL
- Auto-load from URL
- Copy to clipboard

### ✅ Export Searches
- Export as JSON
- Download to file
- Preserves all criteria

## Usage

### Basic Search
1. Navigate to `/search`
2. Fill in search criteria
3. Click "SEARCH"
4. View results

### Save a Search
1. Configure search criteria
2. Click "SAVE SEARCH"
3. Enter a name
4. Click "SAVE"

### Load Saved Search
1. Find search in sidebar
2. Click "LOAD"
3. Search executes automatically

### Share a Search
1. Click "SHARE" on saved search
2. URL copied to clipboard
3. Share link with others
4. Recipients see same search

### Export a Search
1. Click "EXPORT" on saved search
2. JSON file downloads
3. Contains all criteria

## Data Storage

### LocalStorage Keys
- `savedSearches`: Array of saved searches
- `searchHistory`: Array of recent searches (max 20)

### Data Structure

```typescript
// Saved Search
{
  id: string;
  name: string;
  criteria: SearchCriteria;
  createdAt: string;
}

// Search History Item
{
  id: string;
  criteria: SearchCriteria;
  timestamp: string;
  resultCount?: number;
}

// Search Criteria
{
  contract?: string;
  eventType?: string;
  dateFrom?: string;
  dateTo?: string;
  amountMin?: number;
  amountMax?: number;
  status?: string;
}
```

## URL Format

Shareable URLs encode criteria as JSON:
```
/search?criteria=%7B%22eventType%22%3A%22transfer%22%2C%22amountMin%22%3A1000%7D
```

Decoded:
```json
{
  "eventType": "transfer",
  "amountMin": 1000
}
```

## GraphQL Integration

GraphQL queries/mutations defined in `queries/SaveSearch.graphql`:
- `SaveSearch`: Save a search to backend
- `GetSavedSearches`: Fetch user's saved searches
- `DeleteSavedSearch`: Remove a saved search
- `GetSearchHistory`: Fetch search history
- `AddSearchToHistory`: Add search to history

## Utilities

`utils/searchUtils.ts` provides:
- `generateShareableUrl()`: Create shareable URL
- `parseCriteriaFromUrl()`: Parse URL parameters
- `exportSearchAsJson()`: Export as JSON file
- `exportSearchAsCsv()`: Export as CSV file
- `copyToClipboard()`: Copy text to clipboard
- `formatCriteriaAsText()`: Human-readable format

## Styling

Terminal aesthetic with:
- Dark zinc backgrounds
- Monospace fonts
- Green accent colors
- Consistent borders
- Hover states

## Future Enhancements

1. Backend persistence (replace localStorage)
2. User authentication
3. Collaborative shared searches
4. Search templates
5. Advanced filters (regex, wildcards)
6. Scheduled searches
7. Email notifications
8. Search analytics
9. Folder organization
10. Import searches from file

## Testing

To test the feature:
1. Navigate to http://localhost:3000/search
2. Fill in search criteria
3. Save a search
4. Load it from sidebar
5. Share the URL
6. Clear and reload from history
7. Export a search

## Browser Compatibility

- Modern browsers (Chrome, Firefox, Safari, Edge)
- Requires localStorage support
- Clipboard API for sharing
- URL API for parsing
