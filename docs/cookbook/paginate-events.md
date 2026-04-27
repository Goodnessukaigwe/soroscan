# Paginate Events

Use cursor-based pagination to process large event streams safely.

## TypeScript

```typescript
import { SoroScanClient } from "@soroscan/sdk";

const client = new SoroScanClient({ baseUrl: "https://api.soroscan.io" });

let after: string | null = null;
do {
  const page = await client.getEvents({ contractId: "CCAAA...", first: 100, after });
  page.items.forEach((event) => console.log(event.id));
  after = page.pageInfo?.hasNextPage ? page.pageInfo.endCursor : null;
} while (after);
```

## Python

```python
from soroscan import SoroScanClient

client = SoroScanClient(base_url="https://api.soroscan.io")
cursor = None

while True:
    page = client.get_events(contract_id="CCAAA...", first=100, after=cursor)
    for event in page.items:
        print(event.id)
    if not page.page_info.has_next_page:
        break
    cursor = page.page_info.end_cursor
```
