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
from collections import Counter
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
# Bare domains take any 2–24-letter TLD ("scamsite.xyz", "bit.ly/abc123"), all lower- or all
# upper-case so a missing space ("due.Please") is not a domain; file names ("form.pdf") are not.
_FILE_EXT = r"(?:pdf|docx?|jpe?g|png|heic|gif|webp|txt|csv|xlsx?)"
_URL_RE = re.compile(
    r"(?:https?://[^\s<>\"')\]]+)"
    r"|(?<![\w@.-])(?:www\.)?[\w-]+(?:\.[\w-]+)*\."
    rf"(?!{_FILE_EXT}\b)(?-i:[a-z]{{2,24}}|[A-Z]{{2,24}})\b"
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
    schools tax family medical food benefits benefit federal government us united states
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
# "of/for/and <Capitalised …>" after the last institution word belongs to the name ("Department
# of Labor", "Association of Northern Virginia"), unless those words are a language, a weekday or
# a month ("Ask the Clinic for Dari interpreters", "the Court for Monday's hearing").
_TAIL_CONNECTORS = frozenset({"of", "for", "and", "&"})
_TAIL_STOP = frozenset(
    """monday tuesday wednesday thursday friday saturday sunday january february march april may
    june july august september october november december english spanish chinese vietnamese
    tagalog filipino arabic haitian creole portuguese russian ukrainian korean french dari pashto
    persian farsi urdu hindi punjabi bengali somali swahili amharic burmese nepali kinyarwanda
    rohingya tigrinya""".split()
)
_ORG_SUFFIX_KEYS = frozenset(s.casefold() for s in _ORG_SUFFIXES)
# "U.S." / "D.C." / "P.O." → "US" / "DC" / "PO" before punctuation is dropped, so they compare as
# one word ("us" is a generic word) instead of the two tokens "u" and "s".
_INITIALISM_RE = re.compile(r"(?<![\w.])(?:[A-Za-z]\.){2,}")
_AND_SPLIT_RE = re.compile(r"\s+(?:and|&)\s+", re.IGNORECASE)
_PAREN_RE = re.compile(r"\(([^()]*)\)")
_FORMERLY_RE = re.compile(r"^\s*formerly\s+", re.IGNORECASE)
# A replacement right at the start of a sentence gets a capital letter ("An organization …").
_SENTENCE_START_RE = re.compile(r"(?:^\s*|[.!?]\s+|\n\s*)$")
_PUNCT_RE = re.compile(r"[^\w\s]")
_POSSESSIVE_RE = re.compile(r"(?<=\w)['’]s\b")
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
    """NFKC, ``U.S.`` → ``us``, casefold, punctuation → space, collapse whitespace (org/address
    comparison key)."""
    text = unicodedata.normalize("NFKC", text)
    text = _INITIALISM_RE.sub(lambda m: m.group(0).replace(".", ""), text)
    out = _PUNCT_RE.sub(" ", text.casefold())
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


def _ends_sentence(word: str) -> bool:
    """True for a word that closes a sentence or clause ("Labor.", "Center,"); initialisms
    ("U.S.") and single initials ("J.") do not."""
    if word[-1:] in ",;:!?":
        return True
    return word.endswith(".") and len(word) > 2 and not _INITIALISM_RE.fullmatch(word)


def _name_end(words: Sequence[re.Match[str]], last_suffix: int) -> int:
    """Index of the last word of the name whose last institution word is ``words[last_suffix]``:
    trailing "of/for/and <Capitalised …>" groups belong to it ("Department of Immigration
    Payments", "Office of Fast Visas"), up to the end of the sentence."""
    end = last_suffix
    i = end + 1
    while i < len(words) and not _ends_sentence(words[end].group(0)):
        if words[i].group(0).casefold() not in _TAIL_CONNECTORS:
            break
        k = i + 1
        while k < len(words) and words[k].group(0)[:1].isupper():
            if _POSSESSIVE_RE.sub("", words[k].group(0)).casefold().strip(".,;:!?") in _TAIL_STOP:
                break
            k += 1
            if _ends_sentence(words[k - 1].group(0)):
                break
        if k == i + 1:
            break
        end, i = k - 1, k
    return end


def _org_spans(text: str) -> list[ContactMatch]:
    spans: list[ContactMatch] = []
    for run in _CAP_RUN_RE.finditer(text):
        words = list(re.finditer(r"\S+", run.group(0)))
        suffixes = [i for i, w in enumerate(words) if w.group(0).rstrip(".,;:") in _ORG_SUFFIXES]
        if not suffixes:
            continue
        chosen = words[: _name_end(words, suffixes[-1]) + 1]
        while chosen and chosen[0].group(0).casefold().strip(".,;:") in _LEADING_STOP:
            chosen = chosen[1:]
        if len(chosen) < 2:
            continue
        if sum(1 for w in chosen if w.group(0)[:1].isupper()) < 2:
            continue
        start = run.start() + chosen[0].start()
        stop = run.start() + chosen[-1].end()
        # A closing "." is the sentence's, unless the sentence goes on ("… Inc. can help").
        if text[stop - 1] == "." and not _INITIALISM_RE.fullmatch(chosen[-1].group(0)):
            if not re.match(r"\s+[a-z]", text[stop:]):
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


def _url_parts(text: str) -> tuple[str, str]:
    """``(host, path)`` of a URL or bare domain (lower-case; no scheme, ``www.`` or trailing
    punctuation or slash)."""
    host, _, path = normalize_url(text).partition("/")
    return host.rstrip("."), path.rstrip("/")


def _org_aliases(raw: str) -> set[str]:
    """Normalised whole names under which a DB entry may be named: the full name, the name
    without its parentheses, each parenthesised name ("formerly …" dropped) and the part before
    a subtitle colon ("HHS Office for Civil Rights: Limited English …" → "HHS Office for Civil
    Rights")."""
    names = {raw, _PAREN_RE.sub(" ", raw)}
    names |= {_FORMERLY_RE.sub("", p) for p in _PAREN_RE.findall(raw)}
    names |= {n.split(":", 1)[0] for n in list(names)}
    return {k for k in (normalize_org(n) for n in names) if k}


@dataclass(frozen=True)
class AllowList:
    """What may survive the scrubber: contacts printed on the paper plus DB organisation names."""

    phones: frozenset[str]
    n11: frozenset[str]
    urls: frozenset[tuple[str, str]]
    emails: frozenset[str]
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
        printed = find_contacts(corpus, include_orgs=False)
        phones = {normalize_phone(c.text) for c in printed if c.kind == "phone"}
        phones |= {normalize_phone(m) for m in re.findall(r"\d{10,15}", ascii_digits(corpus))}
        n11 = frozenset(m.group(1) for m in _N11_RE.finditer(corpus))
        orgs = frozenset(a for x in resource_names for a in _org_aliases(x))
        return cls(
            phones=frozenset(p for p in phones if p),
            n11=n11,
            urls=frozenset(_url_parts(c.text) for c in printed if c.kind == "url"),
            emails=frozenset(_norm_compact(c.text) for c in printed if c.kind == "email"),
            word_text=f" {_norm_words(corpus)} ",
            org_names=orgs,
        )

    def allows(self, match: ContactMatch) -> bool:
        """True when ``match`` is printed on the paper (or, for organisations, is in the DB)."""
        if match.kind == "phone":
            return normalize_phone(match.text) in self.phones
        if match.kind == "n11":
            return match.text in self.n11
        if match.kind == "url":
            return self.allows_url(match.text)
        if match.kind == "email":
            return _norm_compact(match.text) in self.emails
        if match.kind == "address":
            key = _norm_words(match.text)
            return bool(key) and f" {key} " in self.word_text
        return self.allows_org(match.text)

    def allows_url(self, url: str) -> bool:
        """The same host as a URL printed on the paper (``irs.co`` ≠ ``irs.com``, ``county.gov``
        ≠ ``fairfaxcounty.gov``) and no path, the printed path, or a whole-segment prefix of it."""
        host, path = _url_parts(url)
        return bool(host) and any(
            h == host and (not path or p == path or p.startswith(f"{path}/")) for h, p in self.urls
        )

    def allows_org(self, name: str) -> bool:
        """Generic institution words, a name on the paper, or a whole DB name pass.

        D-10 / AI_PROMPTS §11.3: a DB name counts only as a whole (``U.S. Department`` is not
        ``U.S. Department of Labor …``); a name counts as printed only when its words (from the
        first specific word through the institution suffix) sit together as one stretch of the
        paper, in order or reordered within that stretch ("Immigration Court, Arlington" for
        "Arlington Immigration Court"). Specific words scattered over the page plus generic
        institution words ("Fairfax County Legal Aid Society" on a Department of Family Services
        letter) never pass. Two names joined by "and" ("Legal Aid Justice Center and CASA") pass
        when each one does.
        """
        if self._allows_one_org(name):
            return True
        for m in _AND_SPLIT_RE.finditer(name):
            left, right = name[: m.start()], name[m.end() :]
            if left.strip() and right.strip() and self._allows_one_org(left):
                if self.allows_org(right):
                    return True
        return False

    def _allows_one_org(self, name: str) -> bool:
        words = _norm_words(_POSSESSIVE_RE.sub("", name)).split()  # "Doctor's" → "doctor"
        if all(w in GENERIC_ORG_WORDS for w in words):
            return True
        key = normalize_org(name)
        if not key or f" {key} " in self.word_text or key in self.org_names:
            return True
        core = key.split()
        core = core[next((i for i, w in enumerate(core) if w not in GENERIC_ORG_WORDS), 0) :]
        if self._printed_together(core):
            return True
        # Trailing generic words the paper does not print: "U.S. Citizenship and Immigration
        # Services Office" is printed when "… Immigration Services" is (the rest must still end
        # in an institution word, so "Fairfax Immigration Court" never shrinks to "Fairfax").
        while len(core) > 1 and core[-1] in GENERIC_ORG_WORDS:
            core = core[:-1]
            if core[-1] in _ORG_SUFFIX_KEYS and self._printed_together(core):
                return True
        return False

    def _printed_together(self, core: list[str]) -> bool:
        """True when some run of ``len(core)`` consecutive paper words is exactly ``core``'s
        words (as a multiset, so a printed "Court, Arlington" matches "Arlington Court")."""
        if not core:
            return False
        if f" {' '.join(core)} " in self.word_text:
            return True
        paper = self.word_text.split()
        size, target = len(core), Counter(core)
        return any(
            paper[i] in target and Counter(paper[i : i + size]) == target
            for i in range(len(paper) - size + 1)
        )


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

    def would_change(self, text: str) -> bool:
        """True when ``scrub(text)`` would replace anything; the counts are left alone, so text
        that is dropped rather than shown (clerk card checks) never inflates
        ``verification.contacts_stripped``."""
        result = scrub_text(text, self.allow, marker=self.marker, org_marker=self.org_marker)
        return result.text != text

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
