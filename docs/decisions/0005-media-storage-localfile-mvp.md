# 0005 Media Storage: LocalFileMediaStore MVP, MinIO Optional Future

Date: 2026-06-12

## Status

Accepted

## Context

The MVP must run simply on a laptop, workstation, mini server, or LAN host.
Raw videos and generated assets may live on SSD, HDD, or external HDD.

## Decision

Use `LocalFileMediaStore` for MVP. Treat MinIO as an optional future adapter,
not part of MVP.

## Alternatives Considered

1. Mandatory MinIO from day one.
2. Hardcoded local paths without a media-store abstraction.
3. Cloud object storage as the primary media source.

## Consequences

Positive:

- Minimizes MVP setup complexity.
- Preserves a clean path for future MinIO support.
- Fits local-first deployment targets.

Tradeoffs:

- Remote object-store workflows are deferred.
- Media URI abstraction still needs to be designed early.

## Follow-Up

- Keep media URI resolution in backend contracts.
- Treat MinIO as post-MVP or optional adapter work.
