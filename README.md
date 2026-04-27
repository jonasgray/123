# Suture Price Agent

This repository contains a small Python agent for surgical-center procurement teams that want to compare suture prices across vendor websites. It is tuned for a Beverly Hills surgical center and focuses on quality clinical candidates rather than the absolute cheapest listing.

## What the agent does

- Fetches product or search-result URLs from multiple vendor websites.
- Extracts product name, listed price, package quantity, and source vendor.
- Normalizes every offer to cost per suture and estimated total for a target purchase size.
- Scores quality signals such as known manufacturers, sterile labeling, needle details, USP sizing, and FDA/human-use language.
- Flags offers that look inappropriate for clinical use, including training, practice, expired, veterinary, or non-sterile language.
- Produces a ranked report with Beverly Hills procurement reminders for shipping, tax, lot dating, return policy, and contract or GPO pricing.

## Run it

```bash
python3 -m suture_price_agent \
  --target-sutures 72 \
  --shipping 12.95 \
  --shipping 0 \
  "https://example-medical-supply.test/ethicon-vicryl-box-36" \
  "https://example-distributor.test/covidien-silk-box-12"
```

Each `--shipping` value is matched by position to the URL list. Shipping is optional; when omitted, the report marks shipping, tax, and Beverly Hills delivery terms as needing vendor confirmation.

## Use it from Python

```python
from suture_price_agent import ResearchSource, SuturePriceAgent, format_report

sources = [
    ResearchSource(
        url="https://example-medical-supply.test/ethicon-vicryl-box-36",
        shipping=12.95,
        notes=("Verify current lot date before ordering.",),
    ),
    "https://example-distributor.test/covidien-silk-box-12",
]

agent = SuturePriceAgent(target_sutures=72)
report = agent.research(sources)
print(format_report(report))
```

## Procurement caveat

The agent provides research support, not a final clinical purchasing decision. Before ordering sutures for patient care, confirm sterile human-use labeling, manufacturer authenticity, expiration dates, lot traceability, return terms, sales tax, delivery timing to Beverly Hills, and any negotiated contract or GPO pricing.
