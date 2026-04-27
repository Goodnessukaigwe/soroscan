# GraphQL Advanced Queries

GraphQL helps you fetch nested contract and event data in one round trip.

## Query Events with Contract Metadata

```graphql
query ContractEvents($id: String!, $first: Int!) {
  contract(id: $id) {
    id
    name
    events(first: $first) {
      edges {
        node {
          eventType
          ledger
          txHash
          data
        }
      }
    }
  }
}
```

## Tips

- Request only the fields you need.
- Use variables to keep queries reusable.
- Add pagination arguments (`first`, `after`) for large datasets.
