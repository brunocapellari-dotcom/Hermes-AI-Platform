# Hermes scope — AgroLog Commercial Release 2026-10-09

Hermes is deliberately bounded to reliable orchestration for this release. This change does not attempt to complete the full Hermes platform.

The executable contract defines SOURCE_AVAILABLE, DOCUMENT_INGESTED, DATASET_UPDATED, WEATHER_RUN_AVAILABLE, FREIGHT_EVENT_READY, REPORT_UPDATED and SOURCE_FAILED. The transport-neutral dispatcher provides idempotency, bounded retries, structured failure results and per-delivery timing/attempt telemetry so a failing source does not crash unrelated flows.

Priority E2E paths remain SOURCE UPDATE → EVENT → PROCESSOR → AGROLOG → REPORT and FREIGHT EVENT → EVENT → AGROLOG → REPORT. A simpler stable integration may bypass incomplete Hermes subsystems; Hermes must not become an artificial release dependency.
