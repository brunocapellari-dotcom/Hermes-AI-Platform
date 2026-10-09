# Hermes scope — AgroLog Commercial Release 2026-10-09

Hermes is deliberately bounded to reliable orchestration for this release. This change does not attempt to complete the full Hermes platform.

The executable contract defines SOURCE_AVAILABLE, DOCUMENT_INGESTED, DATASET_UPDATED, WEATHER_RUN_AVAILABLE, FREIGHT_EVENT_READY, REPORT_UPDATED and SOURCE_FAILED. It also defines only the seven release jobs: current collection, historical backfill, weather update, report ingestion, freight processing, report generation and health checks, each with an explicit timeout budget.

The transport-neutral dispatcher provides idempotency, bounded exponential backoff, structured dead-letter handling, per-event circuit isolation, source/correlation telemetry, latency/attempt counters and last-success tracking. A failing source therefore cannot crash unrelated release flows.

Contract E2E tests prove both priority paths can reach REPORT_UPDATED without duplicate delivery: SOURCE UPDATE → EVENT → PROCESSOR → AGROLOG → REPORT and FREIGHT EVENT → EVENT → AGROLOG → REPORT. Live cross-service execution evidence is still required before the release gate may be marked DONE.

A simpler stable integration may bypass incomplete Hermes subsystems; Hermes must not become an artificial release dependency.
