# ADR 0004: Hand-written UI primitives; picture element instead of next/image

- Status: Accepted
- Date: 2026-11-16
- Source: Blueprint v4.0 section 0.2 and the Phase 0 audit

## Context
Older docs chose shadcn/ui + Tailwind and next/image.

## Decision
Hand-written primitives in `apps/web/src/components/ui`, styled with CSS modules and the tokens in `styles/tokens.css`. Images use `<picture>` with AVIF/WebP renditions (320/640/1080) produced by the media worker; `images.unoptimized` is on.

## Consequences
Small bundle, no runtime image resizing. A component framework requires a new ADR.
