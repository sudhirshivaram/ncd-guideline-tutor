"""Catalog of WHO NCD knowledge sources shipped in data/."""

from __future__ import annotations

from typing import Any


DOCUMENT_CATALOG: dict[str, dict[str, Any]] = {
    "WHO-NMH-NVI-18.2-eng.pdf": {
        "doc_id": "hearts-protocols-2018",
        "title": "HEARTS technical package: evidence-based treatment protocols",
        "short_title": "HEARTS protocols",
        "year": 2018,
        "publisher": "WHO",
        "doc_type": "technical_package",
        "ncd_types": [
            "CVD",
            "hypertension",
            "diabetes"
        ],
        "audience": "primary_health_care",
        "source_family": "clinical_protocols"
    },
    "WHO-UCN-NCD-20.1-eng.pdf": {
        "doc_id": "hearts-d-diabetes-2020",
        "title": "Diagnosis and management of type 2 diabetes (HEARTS-D)",
        "short_title": "HEARTS-D diabetes",
        "year": 2020,
        "publisher": "WHO",
        "doc_type": "technical_package",
        "ncd_types": [
            "diabetes"
        ],
        "audience": "primary_health_care",
        "source_family": "clinical_protocols"
    },
    "9789240033986-eng.pdf": {
        "doc_id": "who-htn-guideline-2021",
        "title": "Guideline for the pharmacological treatment of hypertension in adults",
        "short_title": "Hypertension guideline",
        "year": 2021,
        "publisher": "WHO",
        "doc_type": "guideline",
        "ncd_types": [
            "hypertension",
            "CVD"
        ],
        "audience": "primary_health_care",
        "source_family": "clinical_protocols"
    }
}


def catalog_by_doc_id() -> dict[str, dict[str, Any]]:
    return {meta["doc_id"]: {"filename": filename, **meta} for filename, meta in DOCUMENT_CATALOG.items()}


def lookup_filename(filename: str) -> dict[str, Any]:
    if filename not in DOCUMENT_CATALOG:
        raise KeyError(f"Unknown knowledge source: {filename}")
    return {"filename": filename, **DOCUMENT_CATALOG[filename]}
