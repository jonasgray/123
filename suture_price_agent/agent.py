from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import re
from typing import Iterable, Protocol
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_LOCATION = "Beverly Hills, CA"
DEFAULT_TARGET_SUTURES = 36

QUALITY_TERMS = {
    "ethicon": 12,
    "johnson & johnson": 12,
    "covidien": 10,
    "medtronic": 10,
    "stryker": 8,
    "synthetic absorbable": 8,
    "absorbable": 5,
    "non-absorbable": 5,
    "nonabsorbable": 5,
    "sterile": 8,
    "reverse cutting": 4,
    "taper": 4,
    "monofilament": 4,
    "braided": 4,
    "needle": 5,
    "fda": 10,
    "usp": 6,
}

CAUTION_TERMS = {
    "training": "training-use language",
    "practice": "practice-use language",
    "expired": "expired product language",
    "veterinary": "veterinary-use language",
    "not for human": "not-for-human-use language",
    "non-sterile": "non-sterile language",
    "non sterile": "non-sterile language",
}


class SutureResearchError(RuntimeError):
    """Raised when a source cannot be researched or parsed."""


class PageClient(Protocol):
    def fetch(self, url: str) -> str:
        """Return raw page content for a product or search result URL."""


class UrlPageClient:
    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def fetch(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": (
                    "suture-price-agent/1.0 "
                    "(surgical supply price comparison; contact procurement team)"
                )
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")


@dataclass(frozen=True)
class ResearchSource:
    url: str
    label: str | None = None
    shipping: float | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SutureOffer:
    vendor: str
    product_name: str
    url: str
    price: float
    quantity: int
    cost_per_suture: float
    estimated_total: float
    quality_score: int
    caution_flags: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    shipping: float | None = None

    @property
    def is_clinical_candidate(self) -> bool:
        return not self.caution_flags and self.quality_score >= 20


@dataclass(frozen=True)
class SutureResearchReport:
    location: str
    target_sutures: int
    offers: tuple[SutureOffer, ...]
    best_value: SutureOffer | None
    clinical_candidates: tuple[SutureOffer, ...]
    rejected: tuple[SutureOffer, ...]
    searched_urls: tuple[str, ...]
    errors: tuple[str, ...] = ()


class SuturePriceAgent:
    def __init__(
        self,
        client: PageClient | None = None,
        location: str = DEFAULT_LOCATION,
        target_sutures: int = DEFAULT_TARGET_SUTURES,
    ):
        if target_sutures <= 0:
            raise ValueError("target_sutures must be greater than zero.")
        self.client = client or UrlPageClient()
        self.location = location
        self.target_sutures = target_sutures

    def research(self, sources: Iterable[str | ResearchSource]) -> SutureResearchReport:
        normalized_sources = tuple(_normalize_source(source) for source in sources)
        if not normalized_sources:
            raise ValueError("At least one source URL is required.")

        offers: list[SutureOffer] = []
        errors: list[str] = []

        for source in normalized_sources:
            try:
                html = self.client.fetch(source.url)
                offers.append(self._extract_offer(source, html))
            except (OSError, UnicodeError) as exc:
                errors.append(f"{source.url}: {_fetch_error_message(exc)}")
            except SutureResearchError as exc:
                errors.append(f"{source.url}: {exc}")

        ranked = tuple(sorted(offers, key=_rank_offer))
        clinical_candidates = tuple(offer for offer in ranked if offer.is_clinical_candidate)
        rejected = tuple(offer for offer in ranked if not offer.is_clinical_candidate)

        return SutureResearchReport(
            location=self.location,
            target_sutures=self.target_sutures,
            offers=ranked,
            best_value=clinical_candidates[0] if clinical_candidates else None,
            clinical_candidates=clinical_candidates,
            rejected=rejected,
            searched_urls=tuple(source.url for source in normalized_sources),
            errors=tuple(errors),
        )

    def _extract_offer(self, source: ResearchSource, html: str) -> SutureOffer:
        text = _html_to_text(html)
        product_name = _extract_product_name(html, text)
        price = _extract_price(text)
        quantity = _extract_quantity(text)
        vendor = source.label or _vendor_from_url(source.url)
        quality_score, evidence = _score_quality(text, product_name)
        caution_flags = _find_cautions(text)
        shipping = source.shipping
        estimated_total = _estimate_total(price, quantity, self.target_sutures, shipping)

        notes = list(source.notes)
        if shipping is None:
            notes.append("Shipping, tax, contract tier pricing, and Beverly Hills delivery terms require vendor confirmation.")
        else:
            notes.append(f"Includes entered shipping estimate of ${shipping:.2f}.")

        return SutureOffer(
            vendor=vendor,
            product_name=product_name,
            url=source.url,
            price=price,
            quantity=quantity,
            cost_per_suture=round(price / quantity, 2),
            estimated_total=estimated_total,
            quality_score=quality_score,
            caution_flags=caution_flags,
            evidence=evidence,
            notes=tuple(notes),
            shipping=shipping,
        )


def _normalize_source(source: str | ResearchSource) -> ResearchSource:
    if isinstance(source, ResearchSource):
        return source
    return ResearchSource(url=source)


def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    parser.close()
    text = " ".join(parser.text())
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _extract_product_name(html: str, text: str) -> str:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        title = _clean_title(_html_to_text(title_match.group(1)))
        if title:
            return title

    heading_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    if heading_match:
        heading = _clean_title(_html_to_text(heading_match.group(1)))
        if heading:
            return heading

    return _shorten(text, 90) or "Unknown suture product"


def _extract_price(text: str) -> float:
    matches = re.findall(r"(?<![A-Za-z])\$\s*([0-9][0-9,]*(?:\.[0-9]{2})?)", text)
    prices = [float(match.replace(",", "")) for match in matches]
    plausible_prices = [price for price in prices if 0.5 <= price <= 5000]
    if not plausible_prices:
        raise SutureResearchError("No plausible product price found.")
    return min(plausible_prices)


def _extract_quantity(text: str) -> int:
    patterns = (
        r"(?:box|case|pack|package|pkg)\s+of\s+([0-9]{1,4})",
        r"([0-9]{1,4})\s*(?:/|per)\s*(?:box|case|pack|package|pkg)",
        r"([0-9]{1,4})\s*(?:count|ct|pieces|pcs|sutures|strands)",
        r"qty\.?\s*[:#]?\s*([0-9]{1,4})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            quantity = int(match.group(1))
            if quantity > 0:
                return quantity

    return 1


def _score_quality(text: str, product_name: str) -> tuple[int, tuple[str, ...]]:
    haystack = f"{product_name} {text}".casefold()
    score = 0
    evidence: list[str] = []

    for term, points in QUALITY_TERMS.items():
        if term in haystack:
            score += points
            evidence.append(term)

    return min(score, 100), tuple(evidence)


def _find_cautions(text: str) -> tuple[str, ...]:
    haystack = text.casefold()
    flags: list[str] = []
    for term, reason in CAUTION_TERMS.items():
        if term in haystack and reason not in flags:
            flags.append(reason)
    return tuple(flags)


def _estimate_total(price: float, quantity: int, target_sutures: int, shipping: float | None) -> float:
    boxes_needed = -(-target_sutures // quantity)
    total = price * boxes_needed
    if shipping is not None:
        total += shipping
    return round(total, 2)


def _rank_offer(offer: SutureOffer) -> tuple[int, float, int, str]:
    clinical_penalty = 0 if offer.is_clinical_candidate else 1
    return (clinical_penalty, offer.estimated_total, -offer.quality_score, offer.vendor.casefold())


def _vendor_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if not host:
        return "Unknown vendor"
    return host.split(":")[0]


def _clean_title(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -|\t\r\n")
    return _shorten(value, 120)


def _shorten(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


def _fetch_error_message(exc: OSError) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code}"
    reason = getattr(exc, "reason", exc)
    return str(reason).strip() or exc.__class__.__name__


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def format_report(report: SutureResearchReport) -> str:
    lines = [
        f"Suture price research for {report.location}",
        f"Target purchase size: {report.target_sutures} sutures",
        "",
    ]

    if report.best_value:
        lines.extend(
            [
                "Best clinical value:",
                _format_offer(report.best_value, rank=None),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Best clinical value: No source met the minimum quality screen.",
                "",
            ]
        )

    if report.clinical_candidates:
        lines.append("Clinical candidates:")
        for index, offer in enumerate(report.clinical_candidates, start=1):
            lines.append(_format_offer(offer, rank=index))
            lines.append("")

    if report.rejected:
        lines.append("Needs review or rejection:")
        for offer in report.rejected:
            lines.append(_format_offer(offer, rank=None))
            lines.append("")

    if report.errors:
        lines.append("Research errors:")
        lines.extend(f"- {error}" for error in report.errors)
        lines.append("")

    lines.append("Procurement reminder: verify sterile human-use labeling, lot dating, return policy, tax, shipping, and any GPO or contract pricing before ordering.")
    return "\n".join(lines).rstrip()


def _format_offer(offer: SutureOffer, rank: int | None) -> str:
    prefix = f"{rank}. " if rank is not None else "- "
    lines = [
        f"{prefix}{offer.vendor}: {offer.product_name}",
        f"  Price: {_format_money(offer.price)} for {offer.quantity} ({_format_money(offer.cost_per_suture)} each)",
        f"  Estimated total: {_format_money(offer.estimated_total)}",
        f"  Quality score: {offer.quality_score}/100",
        f"  Source: {offer.url}",
    ]
    if offer.evidence:
        lines.append(f"  Quality signals: {', '.join(offer.evidence)}")
    if offer.caution_flags:
        lines.append(f"  Cautions: {', '.join(offer.caution_flags)}")
    for note in offer.notes:
        lines.append(f"  Note: {note}")
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
        description="Research suture product pages and compare price, quality signals, and Beverly Hills procurement fit."
    )
    parser.add_argument("urls", nargs="+", help="Product or search result URLs to research.")
    parser.add_argument("--location", default=DEFAULT_LOCATION, help="Surgical center location for procurement notes.")
    parser.add_argument("--target-sutures", type=int, default=DEFAULT_TARGET_SUTURES, help="Number of sutures to price.")
    parser.add_argument(
        "--shipping",
        type=float,
        action="append",
        default=[],
        help="Optional shipping estimate for the URL at the same position; repeat for multiple URLs.",
    )
    args = parser.parse_args(argv)

    sources = []
    for index, url in enumerate(args.urls):
        shipping = args.shipping[index] if index < len(args.shipping) else None
        sources.append(ResearchSource(url=url, shipping=shipping))

    try:
        report = SuturePriceAgent(location=args.location, target_sutures=args.target_sutures).research(sources)
    except ValueError as exc:
        parser.exit(2, f"Error: {exc}\n")

    print(format_report(report))
    return 1 if report.errors and not report.offers else 0
