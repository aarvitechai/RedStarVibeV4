# ADR 0013: Roles plus a central permission map

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Older docs had user, admin and superadmin only.

## Decision
Roles: user, business, staff, admin, superadmin. One permission map in `app/core/permissions.py`; routes use `require_permission()`, services check object ownership. Superadmins are created only via `scripts/make_superadmin.py`.

## Consequences
Business staff permissions are additionally scoped to one business_id.
