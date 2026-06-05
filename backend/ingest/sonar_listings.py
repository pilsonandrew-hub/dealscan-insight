"""Sonar listings row helpers for ingest."""

from __future__ import annotations

from typing import Any


def build_sonar_listing_row(vehicle: dict[str, Any]) -> dict[str, Any]:
    return {
        "listing_id": vehicle.get("listing_id"),
        "source": vehicle.get("source") or vehicle.get("source_site"),
        "title": vehicle.get("title"),
        "year": vehicle.get("year"),
        "make": vehicle.get("make"),
        "model": vehicle.get("model"),
        "trim": vehicle.get("trim"),
        "mileage": vehicle.get("mileage"),
        "state": vehicle.get("state"),
        "city": vehicle.get("city"),
        "current_bid": float(vehicle.get("current_bid") or 0),
        "auction_end_date": vehicle.get("auction_end_date") or vehicle.get("auction_end_time"),
        "listing_url": vehicle.get("listing_url"),
        "image_url": vehicle.get("image_url") or vehicle.get("photo_url"),
        "photo_url": vehicle.get("photo_url") or vehicle.get("image_url"),
        "agency_name": vehicle.get("agency_name") or vehicle.get("issuing_agency"),
        "condition": vehicle.get("condition"),
        "title_status": vehicle.get("title_status"),
        "vin": vehicle.get("vin"),
        "source_site": vehicle.get("source_site") or vehicle.get("source"),
        "dos_score": vehicle.get("dos_score"),
    }
