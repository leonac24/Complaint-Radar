# Complaint Radar. Backend commands run through uv inside backend/.
RADAR := cd backend && uv run python -m radar.cli
EXPORTS ?= recent

.PHONY: setup data data-fixtures pipeline api web test

setup:
	cd backend && uv sync

## Download and normalize the CFPB archive (EXPORTS=recent|all|2026-07,...)
data:
	$(RADAR) ingest --exports $(EXPORTS)

## Synthetic data for local development (no network)
data-fixtures:
	cd backend && uv run python -m tests.fixtures ../data/raw/fixtures
	$(RADAR) ingest --from-dir ../data/raw/fixtures

## Statistical steps (AI steps are added in milestone 3)
pipeline:
	$(RADAR) emergence
	$(RADAR) templating

api:
	cd backend && uv run uvicorn radar.api:app --reload --port 8000

web:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q
