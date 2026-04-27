# Migrate from REST to GraphQL

Use this guide when your integration outgrows endpoint-by-endpoint REST fetching.

## When to Migrate

- You need nested data in a single request.
- You want tighter payload control.
- You are joining contract + events + transaction metadata.

## Mapping Strategy

1. Start from your current REST response shape.
2. Build an equivalent GraphQL query with only needed fields.
3. Move one feature area at a time (read paths first).

## Example

REST flow:

- `GET /contracts/{id}/`
- `GET /contracts/{id}/events/`

GraphQL replacement:

```graphql
query ContractWithEvents($id: String!) {
  contract(id: $id) {
    id
    name
    events(first: 25) {
      edges {
        node {
          eventType
          txHash
          ledger
        }
      }
    }
  }
}
```
