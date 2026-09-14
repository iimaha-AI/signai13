> Historical review. Runtime repairs and current verification are documented in [README](../README.md), section Runtime repair — 2026-09-14.

# Source review — 2026-09-13

## Strength

Flask + TensorFlow/MediaPipe application with separated inference and database modules.

## Findings

Tracked development .env overrides environment values; no root README; active-model metric null; custom CNN test accuracy 5.15%; in-memory state with multiple workers; training data and end-to-end tests absent.

## Changes in this pass

README documentation now describes the checked-in source and known limitations. Local environment/cache ignore patterns were added without hiding required datasets or serialized test fixtures. Only confirmed OS metadata and Python bytecode were removed where present. Existing application/model logic is unchanged.

## Remaining work

Document active weight provenance and signer-independent evaluation; review environment precedence, worker state, CSRF/auth flows, and refactor the large route module with integration tests.

## Portfolio decision

Improve; strongest AI product candidate, pin after runtime validation.

## Validation scope

Tracked-file inventory, Python syntax inspection, notebook JSON/code inspection, and path/schema checks were performed. This is not a claim of a full application, camera, cloud, training, or database integration run. Runtime-specific results are recorded in the account review report. Existing licenses and differing notebook checkpoints are retained. Bulk deletions, privacy changes, data/schema changes and model retraining require a separate decision.

## Additional source findings

`database/schema.sql` still uses MySQL syntax, while the application initializes PostgreSQL through `db_manager.py`; do not execute that reference SQL against PostgreSQL. The admin training route points to absent `fast_train.py`. Both require coordinated runtime changes. Five PredictionBuffer behavior cases passed without TensorFlow/database access; all three browser JavaScript files passed Node syntax checking.
