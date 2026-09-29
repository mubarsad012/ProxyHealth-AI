"""Contact scrubber (D-10; AI_PROMPTS §11.3): contacts only from the paper or the vetted DB.

Runs over every *model-authored* user-facing string (summary, demand text, plan steps, glossary,
model red flags, questions, ``clerk_need_en``, chat answers, troubleshoot text). Phone numbers
(NANP, international, N11 codes next to a call/dial/text word), URLs and bare domains, e-mails and
US street addresses survive only when they appear on the paper (the transcript, or ``screen_text``
for troubleshoot); everything else becomes the target-language marker
``warning.contacts_stripped_inline`` ("[contact removed — see Get help nearby]"). Capitalised
organisation names ending in an institution word (``… Center``, ``… Legal Aid``, ``… Inc``) that are
neither on the paper nor in ``ResourceRepo.names()`` become ``warning.org_removed_inline``
("an organization (see Get help nearby)"). Emergency numbers in model text are stripped like any
other number — the fixed emergency card carries them.

Verbatim fields (``value_verbatim``, ``source_quote``, ``original_text``) are never passed here.
Pure functions; nothing is logged.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal, overload

from proxyhealth_api.analysis.i18n import Translator
from proxyhealth_api.analysis.verify import ascii_digits
from proxyhealth_api.contracts.enums import WarningCode

MARKER_KEY = "warning.contacts_stripped_inline"
ORG_MARKER_KEY = "warning.org_removed_inline"

ContactKind = Literal["phone", "n11", "url", "email", "address", "org"]

_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_RE = re.compile(
    r"(?:https?://[^\s<>\"')\]]+)"
    r"|(?<![\w@.-])(?:www\.)?[\w-]+(?:\.[\w-]+)*\.(?:gov|org|com|net|us|edu|info|mil|io|co)\b"
    r"(?:/[^\s<>\"')\]]*)?",
    re.IGNORECASE,
)
_NANP_RE = re.compile(r"(?<![\w+])(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\w)")
_INTL_RE = re.compile(r"(?<![\w+])\+\d[\d\s.()-]{6,18}\d(?!\w)")
_N11_RE = re.compile(r"(?<![\w-])(211|311|511|711|811|911|988)(?![\w-])")
_N11_CUE_RE = re.compile(
    r"\b(call|calls|calling|dial|dialing|text|texting|phone|ring|contact|"
    r"llam\w*|marc\w*|mensaje|texto|tel[eé]fono)\b[^.\n]{0,20}$",
    re.IGNORECASE,
)
_STREET_SUFFIX = r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Dr|Drive|Ln|Lane|Suite|Ste)"
_ADDRESS_RE = re.compile(
    r"(?<![\w-])\d{1,6}\s+[A-Z0-9][\w'.-]*(?:\s+[A-Z0-9][\w'.-]*){0,3}\s+" + _STREET_SUFFIX
    + r"\b\.?(?:\s*(?:#|Suite|Ste\.?|Apt\.?|Unit)\s*\w+)?"
)
_ORG_SUFFIXES = (
    "Inc", "LLC", "Center", "Centre", "Services", "Hospital", "Clinic", "Court", "Department",
    "Office", "Agency", "Association", "Society", "Foundation", "Aid", "Law",
)  # fmt: skip
_CONNECTORS = r"(?:of|for|and|the|on|in|at|de|del|la|el|los|las|y|&)"
_CAP_WORD = r"[A-Z][\w'&.-]*"
_CAP_RUN_RE = re.compile(rf"\b{_CAP_WORD}(?:\s+(?:{_CONNECTORS}\s+)?{_CAP_WORD})+")
# Words that name a *kind* of institution rather than a specific one: a run made only of these
# ("the Immigration Court", "Social Security Office", "Your Doctor's Office") is left alone.
GENERIC_ORG_WORDS = frozenset(
    """a an the this that your my their our of for and on in at de del la el los las y
    social security immigration court courts office offices department departments health human
    services service post clinic clinics hospital hospitals legal aid center centre law agency
    agencies association society foundation state county city local public housing school
    schools tax family medical food benefits benefit federal government us u.s. united states
    american national district superior circuit general juvenile traffic small claims civil
    criminal board appeals appeal judge doctor doctor's doctors nurse pharmacy pharmacist bank
    welfare labor justice homeland motor vehicles dmv irs uscis ice eoir ssa medicaid medicare
    snap wic chip hhs insurance plan financial assistance billing business front main
    """.split()
)
# Capitalised words that start a sentence or instruction rather than a name ("Ask the …",
# "Try Acme Legal Services"): trimmed off the front of an organisation span, so the verb stays.
_LEADING_STOP = frozenset(
    """ask call visit contact go talk see bring take send write tell find please then if when
    you the this that your our a an at to from with by for in on and or but also first next
    try reach apply email e-mail use get seek choose hire pay phone text mail check consult
    join sign fill submit register request trust avoid never only do don't not maybe
    llame visite pregunte vaya hable lleve envíe el la los las un una su busque
    escriba consulte contacte pida""".split()
)
# A replacement right at the start of a sentence gets a capital letter ("An organization …").
_SENTENCE_START_RE = re.compile(r"(?:^\s*|[.!?]\s+|\n\s*)$")
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")
# An article just before a replaced organisation is absorbed into the replacement, so
# "Visit the Fake Law Center" becomes "Visit an organization (…)", not "Visit the an organization".
_ARTICLE_BEFORE_RE = re.compile(r"(?:(?<=\s)|^)(the|el|la|los|las)\s+$", re.IGNORECASE)


@dataclass(frozen=True)
class ContactMatch:
    """One contact-like span found in a string (``start``/``end`` are offsets into it)."""

    kind: ContactKind
    start: int
    end: int
    text: str


def _norm_words(text: str) -> str:
    """NFKC, casefold, punctuation → space, collapse whitespace (org/address comparison key)."""
    out = _PUNCT_RE.sub(" ", unicodedata.normalize("NFKC", text).casefold())
    return _WS_RE.sub(" ", out).strip()


def _norm_compact(text: str) -> str:
    """NFKC, casefold, all whitespace removed (URL/e-mail comparison key)."""
    return _WS_RE.sub("", unicodedata.normalize("NFKC", text).casefold())


def normalize_phone(text: str) -> str:
    """Digits only (Eastern digits folded); an 11-digit ``1…`` NANP number drops the ``1``."""
    digits = re.sub(r"\D", "", ascii_digits(unicodedata.normalize("NFKC", text)))
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def normalize_url(text: str) -> str:
    """Lower-case host + path without scheme, ``www.`` or trailing punctuation."""
    s = _norm_compact(text)
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    return s.rstrip("/.,;:!?)")


def normalize_org(text: str) -> str:
    """Organisation key: ``_norm_words`` without a leading ``the`` or a trailing ``Inc``/``LLC``."""
    key = re.sub(r"^the\s+", "", _norm_words(text))
    return re.sub(r"\s+(?:inc|llc|corp|co)$", "", key)


def _org_spans(text: str) -> list[ContactMatch]:
    spans: list[ContactMatch] = []
    for run in _CAP_RUN_RE.finditer(text):
        words = list(re.finditer(r"\S+", run.group(0)))
        end_index = -1
        for i, w in enumerate(words):
            bare = w.group(0).rstrip(".,;:")
            if bare in _ORG_SUFFIXES:
                end_index = i
        if end_index < 1:
            continue
        chosen = words[: end_index + 1]
        while chosen and chosen[0].group(0).casefold().strip(".,;:") in _LEADING_STOP:
            chosen = chosen[1:]
        if len(chosen) < 2:
            continue
        if sum(1 for w in chosen if w.group(0)[:1].isupper()) < 2:
            continue
        start = run.start() + chosen[0].start()
        stop = run.start() + chosen[-1].end()
        if text[stop - 1] == ".":
            stop -= 1
        spans.append(ContactMatch("org", start, stop, text[start:stop]))
    return spans


def find_contacts(text: str, *, include_orgs: bool = True) -> list[ContactMatch]:
    """Every contact-like span in ``text``, non-overlapping, in order (longest wins on overlap)."""
    found: list[ContactMatch] = []
    patterns: tuple[tuple[ContactKind, re.Pattern[str]], ...] = (
        ("email", _EMAIL_RE), ("url", _URL_RE), ("phone", _NANP_RE), ("phone", _INTL_RE),
        ("address", _ADDRESS_RE),
    )  # fmt: skip
    for kind, pattern in patterns:
        for m in pattern.finditer(text):
            span = m.group(0)
            if kind in ("url", "email"):
                span = span.rstrip(".,;:!?")
            if span:
                found.append(ContactMatch(kind, m.start(), m.start() + len(span), span))
    for m in _N11_RE.finditer(text):
        if _N11_CUE_RE.search(text[max(0, m.start() - 40) : m.start()]):
            found.append(ContactMatch("n11", m.start(1), m.end(1), m.group(1)))
    if include_orgs:
        found += _org_spans(text)
    found.sort(key=lambda c: (c.start, -(c.end - c.start)))
    out: list[ContactMatch] = []
    for c in found:
        if out and c.start < out[-1].end:
            continue
        out.append(c)
    return out


@dataclass(frozen=True)
class AllowList:
    """What may survive the scrubber: contacts printed on the paper plus DB organisation names."""

    phones: frozenset[str]
    n11: frozenset[str]
    compact_text: str
    word_text: str
    org_names: frozenset[str]

    @classmethod
    def build(
        cls,
        transcript_text: str,
        resource_names: Iterable[str] = (),
        *,
        extra_texts: Iterable[str] = (),
    ) -> AllowList:
        """Allow-list from the transcript (and e.g. troubleshoot ``screen_text`` in ``extra_texts``)
        and ``ResourceRepo.names()`` (raw names; normalised here)."""
        corpus = "\n".join([transcript_text, *extra_texts])
        phones = {
            normalize_phone(c.text)
            for c in find_contacts(corpus, include_orgs=False)
            if c.kind == "phone"
        }
        phones |= {normalize_phone(m) for m in re.findall(r"\d{10,15}", ascii_digits(corpus))}
        n11 = frozenset(m.group(1) for m in _N11_RE.finditer(corpus))
        orgs = frozenset(n for n in (normalize_org(x) for x in resource_names) if n)
        return cls(
            phones=frozenset(p for p in phones if p),
            n11=n11,
            compact_text=_norm_compact(corpus),
            word_text=f" {_norm_words(corpus)} ",
            org_names=orgs,
        )

    def allows(self, match: ContactMatch) -> bool:
        """True when ``match`` is printed on the paper (or, for organisations, is in the DB)."""
        if match.kind == "phone":
            return normalize_phone(match.text) in self.phones
        if match.kind == "n11":
            return match.text in self.n11
        if match.kind in ("url", "email"):
            key = normalize_url(match.text) if match.kind == "url" else _norm_compact(match.text)
            return bool(key) and key in self.compact_text
        if match.kind == "address":
            key = _norm_words(match.text)
            return bool(key) and f" {key} " in self.word_text
        return self.allows_org(match.text)

    def allows_org(self, name: str) -> bool:
        """Generic institution words, a name on the paper, or a (part of a) DB name pass."""
        words = _norm_words(name).split()
        if all(w in GENERIC_ORG_WORDS for w in words):
            return True
        key = normalize_org(name)
        if not key or f" {key} " in self.word_text:
            return True
        if any(key == n or f" {key} " in f" {n} " for n in self.org_names):
            return True
        # Every specific word is printed on the paper ("Immigration Court, Arlington, VA").
        specific = [w for w in words if w not in GENERIC_ORG_WORDS]
        return all(f" {w} " in self.word_text for w in specific)


@dataclass(frozen=True)
class ScrubResult:
    """``scrub_text`` output: the new string and how many spans were replaced, by class."""

    text: str
    contacts: int
    orgs: int


def scrub_text(text: str, allow: AllowList, *, marker: str, org_marker: str) -> ScrubResult:
    """Replace every contact / organisation span not allowed by ``allow`` with its marker.

    Adjacent contacts separated only by whitespace or ``or``/``,`` collapse into one marker.
    """
    if not text:
        return ScrubResult(text, 0, 0)
    pieces: list[str] = []
    last = 0
    contacts = orgs = 0
    prev_contact_end: int | None = None
    for match in find_contacts(text):
        if allow.allows(match):
            continue
        gap = text[last : match.start]
        if match.kind == "org":
            replacement = org_marker
            article = _ARTICLE_BEFORE_RE.search(gap)
            if article:
                gap = gap[: article.start()]
                if article.group(1)[:1].isupper() and replacement[:1].islower():
                    replacement = replacement[:1].upper() + replacement[1:]
            at_start = _SENTENCE_START_RE.search("".join(pieces) + gap) is not None
            if at_start and replacement[:1].islower():
                replacement = replacement[:1].upper() + replacement[1:]
            pieces += [gap, replacement]
            orgs += 1
            prev_contact_end = None
        else:
            contacts += 1
            joinable = prev_contact_end == last and re.fullmatch(r"[\s,/]*(?:or|o)?[\s,/]*", gap)
            if not joinable:
                pieces += [gap, marker]
            prev_contact_end = match.end
        last = match.end
    if not contacts and not orgs:
        return ScrubResult(text, 0, 0)
    pieces.append(text[last:])
    return ScrubResult("".join(pieces), contacts, orgs)


@dataclass
class ContactScrubber:
    """Stateful wrapper the pipeline uses for one result: scrubs strings and keeps the counts.

    ``verification.contacts_stripped`` = ``total`` (invented organisations count as invented
    contacts); ``warnings()`` returns ``[contacts_stripped]`` once anything was replaced.
    """

    allow: AllowList
    marker: str
    org_marker: str
    contacts_stripped: int = 0
    orgs_replaced: int = 0
    _seen: set[str] = field(default_factory=set, repr=False)

    @overload
    def scrub(self, text: str) -> str: ...
    @overload
    def scrub(self, text: None) -> None: ...
    def scrub(self, text: str | None) -> str | None:
        """Scrub one model-authored string (``None`` passes through)."""
        if text is None:
            return None
        result = scrub_text(text, self.allow, marker=self.marker, org_marker=self.org_marker)
        self.contacts_stripped += result.contacts
        self.orgs_replaced += result.orgs
        return result.text

    def scrub_all(self, texts: Sequence[str]) -> list[str]:
        """Scrub every string of a list (``questions_to_ask``, ``cautions`` …)."""
        return [self.scrub(t) for t in texts]

    @property
    def total(self) -> int:
        """Contacts + organisations replaced so far (the ``verification.contacts_stripped``)."""
        return self.contacts_stripped + self.orgs_replaced

    def warnings(self) -> list[WarningCode]:
        """``[WarningCode.contacts_stripped]`` when anything was replaced, else ``[]``."""
        return [WarningCode.contacts_stripped] if self.total else []


def make_scrubber(
    transcript_text: str,
    resource_names: Iterable[str],
    t: Translator,
    *,
    extra_texts: Iterable[str] = (),
) -> ContactScrubber:
    """Build a ``ContactScrubber`` whose markers are in the target language (``t`` = ``t_server``).

    ``resource_names`` is ``ResourceRepo.names()``; ``extra_texts`` adds troubleshoot
    ``screen_text`` lines (or chat history quotes) to what counts as "printed on the paper".
    """
    allow = AllowList.build(transcript_text, resource_names, extra_texts=extra_texts)
    return ContactScrubber(allow=allow, marker=t(MARKER_KEY), org_marker=t(ORG_MARKER_KEY))


def new_contacts(candidate: str, original: str) -> list[ContactMatch]:
    """Phone/URL/e-mail/address spans of ``candidate`` that ``original`` does not contain.

    The phrasing-rewrite check (DOCUMENT_TAXONOMY §8.2 ``contact_like``): a rewrite may keep the
    contacts of the sentence it replaces (already vetted by the scrubber) but never add one.
    """
    found = find_contacts(candidate, include_orgs=False)
    if not found:
        return []
    allow = AllowList.build(original)
    return [c for c in found if not allow.allows(c)]


def has_contact(text: str) -> bool:
    """True when ``text`` contains any phone/URL/e-mail/address-like span (orgs excluded)."""
    return bool(find_contacts(text, include_orgs=False))


__all__ = [
    "GENERIC_ORG_WORDS",
    "MARKER_KEY",
    "ORG_MARKER_KEY",
    "AllowList",
    "ContactMatch",
    "ContactScrubber",
    "ScrubResult",
    "find_contacts",
    "has_contact",
    "make_scrubber",
    "new_contacts",
    "normalize_org",
    "normalize_phone",
    "normalize_url",
    "scrub_text",
]
