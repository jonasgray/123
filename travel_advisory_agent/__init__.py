"""State Department travel advisory lookup agent."""

from .agent import (
    AdvisoryError,
    AdvisoryNotFound,
    StateDepartmentRssClient,
    TravelAdvisory,
    TravelAdvisoryAgent,
)

AdvisoryNotFoundError = AdvisoryNotFound
StateDepartmentTravelAgent = TravelAdvisoryAgent

__all__ = [
    "AdvisoryError",
    "AdvisoryNotFound",
    "AdvisoryNotFoundError",
    "StateDepartmentRssClient",
    "StateDepartmentTravelAgent",
    "TravelAdvisory",
    "TravelAdvisoryAgent",
]
