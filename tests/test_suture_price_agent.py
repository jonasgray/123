from __future__ import annotations

import io
import textwrap
import unittest
from contextlib import redirect_stdout
from urllib.error import URLError

from suture_price_agent import ResearchSource, SuturePriceAgent, format_report
from suture_price_agent.agent import main


ETHICON_PAGE = textwrap.dedent(
    """\
    <html>
      <head><title>Ethicon VICRYL 3-0 Absorbable Sutures | Example Surgical</title></head>
      <body>
        <h1>Ethicon VICRYL 3-0 Absorbable Sutures</h1>
        <p>Sterile synthetic absorbable braided sutures with reverse cutting needle.</p>
        <p>USP size 3-0. Box of 36 sutures.</p>
        <span>$189.00</span>
      </body>
    </html>
    """
)

GENERIC_PAGE = textwrap.dedent(
    """\
    <html>
      <head><title>Generic Nylon Suture Pack</title></head>
      <body>
        <h1>Generic Nylon Suture Pack</h1>
        <p>Sterile non-absorbable monofilament nylon sutures with needle.</p>
        <p>24 count</p>
        <strong>$72.00</strong>
      </body>
    </html>
    """
)

TRAINING_PAGE = textwrap.dedent(
    """\
    <html>
      <head><title>Practice Suture Kit</title></head>
      <body>
        <h1>Practice Suture Kit</h1>
        <p>Training sutures for practice pads, not for human use.</p>
        <p>Qty: 50</p>
        <strong>$25.00</strong>
      </body>
    </html>
    """
)


class FakeClient:
    def __init__(self, pages):
        self.pages = pages

    def fetch(self, url):
        value = self.pages[url]
        if isinstance(value, Exception):
            raise value
        return value


class SuturePriceAgentTest(unittest.TestCase):
    def test_ranks_clinical_value_by_total_cost_after_quality_screen(self):
        agent = SuturePriceAgent(
            client=FakeClient(
                {
                    "https://example-surgical.test/ethicon-vicryl": ETHICON_PAGE,
                    "https://supply.test/generic-nylon": GENERIC_PAGE,
                    "https://training.test/practice-kit": TRAINING_PAGE,
                }
            ),
            target_sutures=36,
        )

        report = agent.research(
            [
                ResearchSource("https://example-surgical.test/ethicon-vicryl", shipping=12.0),
                ResearchSource("https://supply.test/generic-nylon", shipping=8.0),
                ResearchSource("https://training.test/practice-kit", shipping=5.0),
            ]
        )

        self.assertEqual(report.location, "Beverly Hills, CA")
        self.assertEqual(report.best_value.vendor, "supply.test")
        self.assertEqual(report.best_value.cost_per_suture, 3.0)
        self.assertEqual(report.best_value.estimated_total, 152.0)
        self.assertEqual([offer.vendor for offer in report.clinical_candidates], ["supply.test", "example-surgical.test"])
        self.assertEqual(report.rejected[0].vendor, "training.test")
        self.assertIn("not-for-human-use language", report.rejected[0].caution_flags)

    def test_formats_report_with_procurement_reminders_and_quality_signals(self):
        agent = SuturePriceAgent(client=FakeClient({"https://example.test/ethicon": ETHICON_PAGE}))
        report = agent.research(["https://example.test/ethicon"])

        output = format_report(report)

        self.assertIn("Suture price research for Beverly Hills, CA", output)
        self.assertIn("Best clinical value:", output)
        self.assertIn("Quality signals: ethicon", output)
        self.assertIn("verify sterile human-use labeling", output)

    def test_records_fetch_errors_without_losing_successful_sources(self):
        agent = SuturePriceAgent(
            client=FakeClient(
                {
                    "https://example.test/ethicon": ETHICON_PAGE,
                    "https://broken.test/product": URLError("connection refused"),
                }
            )
        )

        report = agent.research(["https://example.test/ethicon", "https://broken.test/product"])

        self.assertEqual(len(report.offers), 1)
        self.assertEqual(len(report.errors), 1)
        self.assertIn("connection refused", report.errors[0])

    def test_cli_prints_report(self):
        class CliAgent(SuturePriceAgent):
            def __init__(self, *args, **kwargs):
                super().__init__(client=FakeClient({"https://example.test/ethicon": ETHICON_PAGE}), *args, **kwargs)

        import suture_price_agent.agent as agent_module

        original_agent = agent_module.SuturePriceAgent
        agent_module.SuturePriceAgent = CliAgent
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                status = main(["https://example.test/ethicon", "--target-sutures", "36"])
        finally:
            agent_module.SuturePriceAgent = original_agent

        self.assertEqual(status, 0)
        self.assertIn("Target purchase size: 36 sutures", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
