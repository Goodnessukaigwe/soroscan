# Advanced Search Feature

Search, save, and share queries with the SoroScan advanced search interface.

## Features

- Multi-criteria search form
- Save searches with custom names
- Search history (last 20)
- Shareable URLs
- Export searches as JSON

## Usage

Navigate to `/search` to access the advanced search interface.

### Search Criteria

- Contract address
- Event type (transfer, mint, burn, approve)
- Date range (from/to)
- Amount range (min/max XLM)
- Transaction status

### Saving Searches

1. Configure your search criteria
2. Click "SAVE SEARCH"
3. Enter a name for your search
4. Click "SAVE"

### Loading Saved Searches

Click "LOAD" on any saved search in the sidebar to quickly reload it.

### Sharing Searches

Click "SHARE" to copy a shareable URL to your clipboard. Anyone with the link can view the same search.

### Search History

Your last 20 searches are automatically saved and can be reloaded with one click.

## Data Storage

Searches are stored in browser localStorage for persistence across sessions.
