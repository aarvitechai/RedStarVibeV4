# ADR 0018: Booking model and module dependencies

- Status: Accepted
- Date: 2026-11-16
- Source: Phase 2 implementation

## Context
Booking needs business data (services, hours, resources), and reviews need both a completed booking and the business owner. Putting reviews inside `business` would make business and booking depend on each other.

## Decision
- Dependency direction: `business` ← `booking` ← `reviews`. `notifications` depends on nothing; it reacts to events whose payloads carry the ids it needs (`business_owner_id`, `customer_id`).
- A bookable **resource** (person, vehicle, chair, lawn) is the unit of the exclusion constraint. Every business starts with one resource ("Owner").
- `slot` = service duration + business buffer, half-open `[start, end)`. Slots step every 30 minutes with a 30-minute lead time, up to 60 days ahead.
- Booking creation tries free resources in order inside savepoints. An exclusion violation (SQLSTATE 23P01) moves to the next resource; none left means 409 `slot_taken`.
- `Idempotency-Key` is required and unique per customer. A replay returns the original booking with HTTP 200.
- States: pending → confirmed → done; pending/confirmed → cancelled; pending → expired (beat job). Customers may cancel only before the start time.

## Consequences
Holidays and one-off closures are not modelled yet (Phase 2 backlog). Staff-specific services and per-resource hours come with the Enterprise plan.
