from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import random
import re
from typing import Iterable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree


TRAVEL_ADVISORY_RSS_URL = "https://travel.state.gov/_res/rss/TAsTWs.xml"

RISK_GUIDELINES = {
    1: (
        "Exercise Normal Precautions",
        "The lowest level of risk, though some safety risks may exist.",
    ),
    2: (
        "Exercise Increased Caution",
        "Be aware of heightened risks to safety and security.",
    ),
    3: (
        "Reconsider Travel",
        "Avoid travel due to serious risks.",
    ),
    4: (
        "Do Not Travel",
        "The highest level of risk, typically indicating life-threatening conditions or a high likelihood of danger.",
    ),
}

GREETINGS = (
    "Hello!",
    "Hi there!",
    "Greetings!",
    "Travel advisory ready.",
)


class AdvisoryError(RuntimeError):
    """Raised when advisory information cannot be fetched or parsed."""


class AdvisoryNotFound(LookupError):
    """Raised when a requested destination is not found in the feed."""


class AdvisoryFeedClient(Protocol):
    def fetch(self) -> str:
        """Return the raw advisory feed XML."""


class StateDepartmentRssClient:
    def __init__(self, url: str = TRAVEL_ADVISORY_RSS_URL, timeout: int = 20):
        self.url = url
        self.timeout = timeout

    def fetch(self) -> str:
        request = Request(self.url, headers={"User-Agent": "travel-advisory-agent/1.0"})
        with urlopen(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8")


@dataclass(frozen=True)
class TravelAdvisory:
    destination: str
    level: int
    label: str
    guidance: str
    published: str
    source_url: str
    summary: str

    @property
    def risk_level(self) -> str:
        return f"Level {self.level} - {self.label}"


class TravelAdvisoryAgent:
    def __init__(self, client: AdvisoryFeedClient | None = None):
        self.client = client or StateDepartmentRssClient()

    def check_destination(self, destination: str) -> TravelAdvisory:
        requested = destination.strip()
        if not requested:
            raise ValueError("Destination is required.")

        advisories = self.list_advisories()
        normalized_request = _normalize_destination(requested)

        for advisory in advisories:
            if _normalize_destination(advisory.destination) == normalized_request:
                return advisory

        for advisory in advisories:
            if normalized_request in _normalize_destination(advisory.destination):
                return advisory

        available = ", ".join(advisory.destination for advisory in advisories[:10])
        raise AdvisoryNotFound(
            f"No State Department advisory found for '{requested}'. "
            f"Try the destination name used by travel.state.gov. Examples: {available}."
        )

    def lookup(self, destination: str) -> TravelAdvisory:
        return self.check_destination(destination)

    def list_advisories(self) -> list[TravelAdvisory]:
        try:
            root = ElementTree.fromstring(self.client.fetch())
        except ElementTree.ParseError as exc:
            raise AdvisoryError("State Department advisory feed returned invalid XML.") from exc
        except OSError as exc:
            raise AdvisoryError(_fetch_error_message(exc)) from exc

        advisories: list[TravelAdvisory] = []
        seen_destinations: set[str] = set()

        for item in root.findall("./channel/item"):
            advisory = _parse_item(item)
            if advisory is None:
                continue

            normalized = _normalize_destination(advisory.destination)
            if normalized in seen_destinations:
                continue

            seen_destinations.add(normalized)
            advisories.append(advisory)

        return advisories


def _parse_item(item: ElementTree.Element) -> TravelAdvisory | None:
    title = _text(item, "title")
    match = re.match(r"^(?P<destination>.+?)\s+-\s+Level\s+(?P<level>[1-4]):\s+(?P<label>.+)$", title)
    if not match:
        return None

    level = int(match.group("level"))
    official_label, guidance = RISK_GUIDELINES[level]
    label = _normalize_label(match.group("label")) or official_label

    return TravelAdvisory(
        destination=match.group("destination").strip(),
        level=level,
        label=label,
        guidance=guidance,
        published=_text(item, "pubDate"),
        source_url=_text(item, "link"),
        summary=_clean_html(_text(item, "description")),
    )


def _text(item: ElementTree.Element, tag: str) -> str:
    element = item.find(tag)
    return (element.text or "").strip() if element is not None else ""


def _normalize_label(label: str) -> str:
    normalized = re.sub(r"\s+", " ", unescape(label)).strip()
    for official_label, _ in RISK_GUIDELINES.values():
        if normalized.lower() == official_label.lower():
            return official_label
    return normalized


def _normalize_destination(destination: str) -> str:
    normalized = unescape(destination).casefold()
    normalized = re.sub(r"&", " and ", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _clean_html(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(unescape(value))
    parser.close()
    text = " ".join(parser.text())
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_error_message(exc: OSError) -> str:
    if isinstance(exc, HTTPError):
        return f"Could not fetch the State Department advisory feed: HTTP {exc.code}."

    reason = getattr(exc, "reason", exc)
    detail = str(reason).strip()
    message = "Could not fetch the State Department advisory feed"
    if detail:
        message = f"{message}: {detail}"

    if "CERTIFICATE_VERIFY_FAILED" in detail or "certificate verify failed" in detail.lower():
        message = (
            f"{message}. On macOS, run the Python 'Install Certificates.command' "
            "application, then try again."
        )

    return f"{message}."


def _shorten(value: str, limit: int = 700) -> str:
    if len(value) <= limit:
        return value

    return value[: limit - 3].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


def _random_greeting() -> str:
    return random.choice(GREETINGS)


def _format_advisory(
    advisory: TravelAdvisory,
    summary_limit: int | None = 700,
    greeting: str | None = None,
) -> str:
    lines = [
        greeting or _random_greeting(),
        f"Destination: {advisory.destination}",
        f"Risk Level: {advisory.risk_level}",
        f"Guidance: {advisory.guidance}",
    ]
    if advisory.published:
        lines.append(f"Published: {advisory.published}")
    if advisory.source_url:
        lines.append(f"Source: {advisory.source_url}")
    if advisory.summary:
        summary = advisory.summary if summary_limit is None else _shorten(advisory.summary, summary_limit)
        lines.append(f"Summary: {summary}")
    return "\n".join(lines)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        clean = data.strip()
        if clean:
            self._chunks.append(clean)

    def text(self) -> Iterable[str]:
        return self._chunks


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Check travel.state.gov for destination-specific travel advisory risk level."
    )
    parser.add_argument("destination", nargs="?", help="Destination name, for example 'Haiti' or 'Hungary'.")
    args = parser.parse_args(argv)
    destination = args.destination or input("Destination: ").strip()

    try:
        advisory = TravelAdvisoryAgent().check_destination(destination)
    except (AdvisoryError, AdvisoryNotFound, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")

    print(_format_advisory(advisory))

    return 0
