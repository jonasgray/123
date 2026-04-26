import io
import ssl
import textwrap
import unittest
from contextlib import redirect_stdout
from urllib.error import URLError

from travel_advisory_agent import (
    AdvisoryError,
    AdvisoryNotFound,
    TravelAdvisoryAgent,
)
from travel_advisory_agent.agent import _format_advisory


SAMPLE_FEED = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>Haiti - Level 4: Do Not Travel</title>
          <link>https://travel.state.gov/haiti</link>
          <description><![CDATA[
            <p>Do Not Travel to Haiti due to the risk of <b>crime</b>,
            <b>terrorism</b>, and <b>kidnapping</b>.</p>
          ]]></description>
          <pubDate>Thu, 16 Apr 2026</pubDate>
        </item>
        <item>
          <title>Hungary - Level 1: Exercise Normal Precautions</title>
          <link>https://travel.state.gov/hungary</link>
          <description>Exercise normal precaution&lt;p&gt;in &lt;b&gt;Hungary&lt;/b&gt;.&lt;/p&gt;</description>
          <pubDate>Wed, 15 Apr 2026</pubDate>
        </item>
        <item>
          <title>Trinidad and Tobago - Level 3: Reconsider Travel</title>
          <link>https://travel.state.gov/trinidad-new</link>
          <description>Reconsider travel due to crime.</description>
          <pubDate>Mon, 13 Apr 2026</pubDate>
        </item>
        <item>
          <title>Trinidad and Tobago - Level 3: Reconsider Travel</title>
          <link>https://travel.state.gov/trinidad-old</link>
          <description>Older duplicate advisory.</description>
          <pubDate>Mon, 01 Apr 2024</pubDate>
        </item>
      </channel>
    </rss>
    """
).encode()


class FakeClient:
    def fetch(self):
        return SAMPLE_FEED.decode()


class StateDepartmentTravelAgentTest(unittest.TestCase):
    def setUp(self):
        self.agent = TravelAdvisoryAgent(client=FakeClient())

    def test_returns_level_guidance_and_clean_summary(self):
        advisory = self.agent.lookup("Haiti")

        self.assertEqual(advisory.destination, "Haiti")
        self.assertEqual(advisory.level, 4)
        self.assertEqual(advisory.label, "Do Not Travel")
        self.assertIn("highest level of risk", advisory.guidance)
        self.assertEqual(advisory.source_url, "https://travel.state.gov/haiti")
        self.assertIn("crime, terrorism, and kidnapping", advisory.summary)

    def test_lookup_normalizes_case_punctuation_and_spacing(self):
        advisory = self.agent.lookup("  trinidad & tobago ")

        self.assertEqual(advisory.destination, "Trinidad and Tobago")
        self.assertEqual(advisory.level, 3)
        self.assertEqual(advisory.source_url, "https://travel.state.gov/trinidad-new")

    def test_returns_all_advisories_once_per_destination(self):
        advisories = self.agent.list_advisories()

        self.assertEqual([advisory.destination for advisory in advisories], ["Haiti", "Hungary", "Trinidad and Tobago"])

    def test_raises_helpful_error_when_destination_is_unknown(self):
        with self.assertRaisesRegex(AdvisoryNotFound, "No State Department advisory found for 'Atlantis'"):
            self.agent.lookup("Atlantis")

    def test_format_advisory_limits_long_summary(self):
        advisory = self.agent.lookup("Haiti")
        output = _format_advisory(advisory, summary_limit=80)

        self.assertIn("Risk Level: Level 4 - Do Not Travel", output)
        self.assertIn("Summary: Do Not Travel to Haiti due to the risk of crime, terrorism, and kidnapping.", output)

    def test_format_advisory_can_print_without_summary_limit(self):
        advisory = self.agent.lookup("Haiti")
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            print(_format_advisory(advisory, summary_limit=None))

        self.assertIn("Source: https://travel.state.gov/haiti", buffer.getvalue())

    def test_fetch_error_includes_underlying_reason(self):
        class BrokenClient:
            def fetch(self):
                raise URLError(ssl.SSLCertVerificationError("certificate verify failed"))

        agent = TravelAdvisoryAgent(client=BrokenClient())

        with self.assertRaisesRegex(AdvisoryError, "certificate verify failed"):
            agent.lookup("Haiti")


if __name__ == "__main__":
    unittest.main()
