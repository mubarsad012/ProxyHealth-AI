# Readability rule for base strings

Every English base string in `apps/api/data/langpacks/en.json` (the source of the packs under
`packs/`) must read at **grade 5 or below** (BUILD_PLAN §1.1 rule 9: "4th-grade reading level, no
dramatizing"). The API CI script `tests/unit/test_readability.py` (WP8) checks this; the mobile
app never rewrites copy at runtime.

Practical rules for anyone adding a key:

1. One idea per sentence. Prefer two short sentences over one long one.
2. Common words: "paper" not "document" where the user sees it; "helper" for the model;
   "phone" for the device (web variants say "browser").
3. No dramatizing words (never "urgent!", "danger", CAPS). Urgency is icon + word + colour.
4. Placeholders use `{snake_case}` and appear exactly once; packs must keep the same set.
5. No emoji anywhere, no markdown, no HTML.
6. Privacy sentences must be literally true per tier (D-02); change them only with a
   `CONSENT_VERSION` bump (COMPLIANCE_PRIVACY §4.7).
7. Buttons ≤ 3 words where possible; screen readers read the whole label.

Requesting a new key: append a `CL-nnn` line to `docs/DECISIONS.md` §14 for WP0, or (during
Phase 1) add it to `en.json` yourself and run `apps/api/scripts/sync_to_mobile.py` so the mobile
copy under `packs/en.json` stays byte-identical.
