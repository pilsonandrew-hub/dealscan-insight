from dataclasses import dataclass
from typing import Optional


@dataclass
class PublicListing:
    source_site: str
    listing_url: str
    auction_end: str
    year: int
    make: str
    model: str
    trim: str
    mileage: int
    current_bid: float
    location: str
    state: str
    vin: Optional[str] = None
    photo_url: Optional[str] = None
    description: Optional[str] = None