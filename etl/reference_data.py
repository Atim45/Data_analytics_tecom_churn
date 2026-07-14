"""
etl/reference_data.py
======================
Static reference/lookup data that is NOT present in the raw CSV but is
required to populate ``dim_telecom_partner`` and ``dim_geography`` fully.

The raw CSV only carries ``telecom_partner`` (a name) and ``state`` / ``city``
/ ``pincode``. The star schema, however, expects additional descriptive
attributes (``partner_code``, ``market_share``, ``technology``, ``hq_city``,
``region``) that are business/reference knowledge, not transactional data.

These mappings are intentionally kept in code (versionable, reviewable) so
the ETL never invents or guesses values silently — anything not covered by
an explicit mapping is logged as a warning and passed through with a safe
default.
"""

from __future__ import annotations

from typing import Dict, TypedDict


class PartnerReference(TypedDict):
    partner_code: str
    market_share: float
    technology: str
    hq_city: str
    founded_year: int
    is_active: bool


# Reference attributes for the four telecom operators present in the source
# CSV. Values are illustrative/approximate industry figures used to fully
# populate dim_telecom_partner's descriptive columns.
TELECOM_PARTNER_REFERENCE: Dict[str, PartnerReference] = {
    "Reliance Jio": {
        "partner_code": "JIO",
        "market_share": 40.00,
        "technology": "5G",
        "hq_city": "Mumbai",
        "founded_year": 2016,
        "is_active": True,
    },
    "Airtel": {
        "partner_code": "ATL",
        "market_share": 33.00,
        "technology": "5G",
        "hq_city": "New Delhi",
        "founded_year": 1995,
        "is_active": True,
    },
    "Vodafone": {
        "partner_code": "VI",
        "market_share": 19.00,
        "technology": "4G",
        "hq_city": "Mumbai",
        "founded_year": 2018,
        "is_active": True,
    },
    "BSNL": {
        "partner_code": "BSNL",
        "market_share": 8.00,
        "technology": "4G",
        "hq_city": "New Delhi",
        "founded_year": 2000,
        "is_active": True,
    },
}

# Fallback used for any telecom_partner value found in the CSV that is not
# in the mapping above. This keeps the pipeline resilient to unexpected new
# operator names instead of crashing, while making the gap visible in logs.
DEFAULT_PARTNER_REFERENCE: PartnerReference = {
    "partner_code": "UNK",
    "market_share": 0.00,
    "technology": "Unknown",
    "hq_city": "Unknown",
    "founded_year": 2000,
    "is_active": True,
}


# Indian state / union territory -> broad geographic region mapping.
# Used to populate dim_geography.region, which has no direct source column.
STATE_TO_REGION: Dict[str, str] = {
    # North
    "Delhi": "North", "Haryana": "North", "Himachal Pradesh": "North",
    "Jammu and Kashmir": "North", "Ladakh": "North", "Punjab": "North",
    "Rajasthan": "North", "Uttarakhand": "North", "Chandigarh": "North",
    "Uttar Pradesh": "North",
    # South
    "Andhra Pradesh": "South", "Karnataka": "South", "Kerala": "South",
    "Tamil Nadu": "South", "Telangana": "South", "Puducherry": "South",
    "Lakshadweep": "South", "Andaman and Nicobar Islands": "South",
    # East
    "Bihar": "East", "Jharkhand": "East", "Odisha": "East",
    "West Bengal": "East",
    # West
    "Goa": "West", "Gujarat": "West", "Maharashtra": "West",
    "Dadra and Nagar Haveli and Daman and Diu": "West",
    # Central
    "Chhattisgarh": "Central", "Madhya Pradesh": "Central",
    # Northeast
    "Arunachal Pradesh": "Northeast", "Assam": "Northeast",
    "Manipur": "Northeast", "Meghalaya": "Northeast", "Mizoram": "Northeast",
    "Nagaland": "Northeast", "Sikkim": "Northeast", "Tripura": "Northeast",
}

DEFAULT_REGION = "Unknown"


def get_partner_reference(partner_name: str) -> PartnerReference:
    """Look up static reference attributes for a telecom partner name."""
    return TELECOM_PARTNER_REFERENCE.get(partner_name, DEFAULT_PARTNER_REFERENCE)


def get_region_for_state(state: str) -> str:
    """Look up the geographic region for an Indian state/UT name."""
    return STATE_TO_REGION.get(state, DEFAULT_REGION)
