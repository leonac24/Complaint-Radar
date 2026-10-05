# Complaint Radar. Backend commands run through uv inside backend/.
RADAR := cd backend && uv run python -m radar.cli
EXPORTS ?= recent

.PHONY: setup data data-fixtures pipeline dry-run api web test

setup:
	cd backend && uv sync

## Download and normalize the CFPB archive (EXPORTS=recent|all|2026-07,...)
data:
	$(RADAR) ingest --exports $(EXPORTS)

## Synthetic data for local development (no network)
data-fixtures:
	cd backend && uv run python -m tests.fixtures ../data/raw/fixtures
	$(RADAR) ingest --from-dir ../data/raw/fixtures

## Every step. extract asks before spending (make pipeline YES=--yes to skip).
pipeline:
	$(RADAR) emergence
	$(RADAR) templating
	$(RADAR) extract --batch $(YES)
	$(RADAR) themes
	$(RADAR) analyst
	$(RADAR) skeptic

## What extract would call and cost, without calling anything
dry-run:
	$(RADAR) extract --dry-run --batch

api:
	cd backend && uv run uvicorn radar.api:app --reload --port 8000

web:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q
