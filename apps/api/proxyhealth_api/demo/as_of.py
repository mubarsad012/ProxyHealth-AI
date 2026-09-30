"""The fixed "today" of the sample papers (D-11/D-12 for demo samples; BUILD_PLAN Appendix D).

Sample papers print fixed dates. Against the wall clock their urgency and "in N days" would drift
and, a few weeks after 2026-10-02, read as past due. So for a sample paper only — a request with
``demo_sample_id``, or an upload the mock matched to a fixture by dHash — ``deadline_rules`` and
``urgency`` run as of ``DEMO_AS_OF``, the date every fixture manifest records as ``today`` and the
date the goldens, Appendix D and the offline bundle (``sync_to_mobile.py``) assume. Real papers
always use the real clock. The mobile app shows one fixed line on sample results
(``demo.as_of_note``) that names this date, so the copy and this constant must change together.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

DEMO_AS_OF = date(2026, 10, 2)
# 14:00 UTC is the same calendar day in every US time zone the goldens use (10:00 EDT, 04:00 HST).
DEMO_AS_OF_MOMENT = datetime.combine(DEMO_AS_OF, time(14, 0), tzinfo=UTC)

__all__ = ["DEMO_AS_OF", "DEMO_AS_OF_MOMENT"]
