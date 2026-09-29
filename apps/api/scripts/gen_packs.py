"""Build, rebase and check the bundled language packs (D-25; BUILD_PLAN §4.3, §5.2 step 6).

Usage (from the repo root)::

    apps/api/.venv/bin/python apps/api/scripts/gen_packs.py --check
        QA every bundled pack (placeholders, length, HTML, digit runs, missing keys); exit 1 on
        any issue. Needs no keys.
    apps/api/.venv/bin/python apps/api/scripts/gen_packs.py --rebase
        After en.json changed: set pack_version to the new base hash, add new keys in English
        (listed in fallback_keys), drop removed keys, recompute etag/coverage. Needs no keys.
    apps/api/.venv/bin/python apps/api/scripts/gen_packs.py --assemble TAG FLAT.json
        Wrap a hand-authored flat {key: translation} map into data/langpacks/TAG.json
        (machine_translated: true, reviewed_by: null). Keys failing QA fall back to English.
    apps/api/.venv/bin/python apps/api/scripts/gen_packs.py [--tags es,prs,...]
        Generate Tier 1+2 packs with MODEL_FAST through the key pool. Needs GEMINI_KEYS
        (exit 2 with a message when empty) and should run on billed keys only.

Packs contain UI strings only — never user content.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proxyhealth_api.contracts.enums import Confidence, PackSource, PackTier  # noqa: E402
from proxyhealth_api.contracts.langpack import LanguagePack  # noqa: E402
from proxyhealth_api.packs.base import BasePack, LanguageTable, pack_etag  # noqa: E402
from proxyhealth_api.packs.qa import check_pack, merge_with_fallback  # noqa: E402
from proxyhealth_api.settings import DATA_DIR, Settings  # noqa: E402

LANGPACKS = DATA_DIR / "langpacks"


def bundled_tags() -> list[str]:
    return sorted(
        p.stem for p in LANGPACKS.glob("*.json") if not p.name.startswith("_") and p.stem != "en"
    )


def write_pack(pack: LanguagePack) -> Path:
    path = LANGPACKS / f"{pack.language_tag}.json"
    data = pack.model_dump(mode="json")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_pack(
    tag: str,
    strings: dict[str, str],
    fallback_keys: list[str],
    base: BasePack,
    languages: LanguageTable,
    *,
    confidence: Confidence = Confidence.medium,
    reviewed_by: str | None = None,
    generated_at: datetime | None = None,
) -> LanguagePack:
    entry = languages.get(tag)
    if entry is None:
        raise SystemExit(f"{tag!r} is not in data/languages.yaml")
    ordered = {key: strings.get(key, english) for key, english in base.strings.items()}
    fallback = sorted(set(fallback_keys) | {k for k in base.strings if k not in strings})
    return LanguagePack(
        language_tag=tag,
        language_name_native=entry.name_native,
        language_name_en=entry.name_en,
        direction=entry.direction,
        script=entry.script,
        digit_system=entry.digit_system,
        font_hint=entry.font_hint,
        tier=entry.tier,
        source=PackSource.bundled,
        pack_version=base.version,
        etag=pack_etag(tag, base.version, ordered),
        strings=ordered,
        fallback_keys=fallback,
        coverage=round(1 - len(fallback) / max(len(ordered), 1), 4),
        machine_translated=True,
        reviewed_by=reviewed_by,
        confidence=confidence,
        generated_at=generated_at or datetime.now(UTC).replace(microsecond=0),
        tts_tag=entry.tts_tag,
        tts_fallback_tag=entry.tts_fallback_tag,
    )


def cmd_check(base: BasePack) -> int:
    failures = 0
    for tag in bundled_tags():
        pack = LanguagePack.model_validate_json((LANGPACKS / f"{tag}.json").read_bytes())
        report = check_pack(base.strings, pack.strings)
        stale = pack.pack_version != base.version
        status = "ok" if report.ok and not stale else "FAIL"
        print(
            f"{tag}: {status} — {len(report.issues)} QA issues, {len(report.missing)} missing, "
            f"{len(pack.fallback_keys)} fallback, pack_version {'stale' if stale else 'current'}"
        )
        for issue in report.issues[:25]:
            print(f"  {issue.key}: {issue.check} ({issue.detail})")
        failures += 0 if status == "ok" else 1
    return 1 if failures else 0


def cmd_rebase(base: BasePack, languages: LanguageTable) -> int:
    for tag in bundled_tags():
        old = LanguagePack.model_validate_json((LANGPACKS / f"{tag}.json").read_bytes())
        kept = {k: v for k, v in old.strings.items() if k in base.strings}
        fallback = [k for k in old.fallback_keys if k in base.strings]
        pack = build_pack(
            tag, kept, fallback, base, languages, confidence=old.confidence,
            reviewed_by=old.reviewed_by, generated_at=old.generated_at,
        )  # fmt: skip
        write_pack(pack)
        print(f"{tag}: rebased, {len(pack.fallback_keys)} fallback keys")
    return 0


def cmd_assemble(tag: str, flat_path: Path, base: BasePack, languages: LanguageTable) -> int:
    flat = json.loads(flat_path.read_text(encoding="utf-8"))
    if not isinstance(flat, dict):
        raise SystemExit(f"{flat_path} must be a flat JSON object")
    translated = {str(k): str(v) for k, v in flat.items() if k in base.strings}
    unknown = sorted(set(flat) - set(base.strings))
    strings, fallback, report = merge_with_fallback(base.strings, translated)
    accepted = {k: v for k, v in strings.items() if k not in fallback}
    pack = build_pack(tag, accepted, fallback, base, languages)
    path = write_pack(pack)
    print(f"{tag}: wrote {path.name}; coverage {pack.coverage}; {len(fallback)} fallback keys")
    for issue in report.issues:
        print(f"  QA {issue.key}: {issue.check} ({issue.detail})")
    if unknown:
        print(f"  ignored keys not in en.json: {unknown[:20]}")
    return 0 if report.ok else 1


async def cmd_generate(tags: list[str], base: BasePack, languages: LanguageTable) -> int:
    settings = Settings()
    if not settings.gemini_keys:
        print(
            "gen_packs.py needs GEMINI_KEYS (billed keys; see apps/api/.env.example). "
            "Without keys, author packs by hand and use --assemble / --rebase / --check.",
            file=sys.stderr,
        )
        return 2
    from proxyhealth_api.ai.failover import AIService
    from proxyhealth_api.ai.gemini import GeminiProvider
    from proxyhealth_api.ai.keypool import KeyPool
    from proxyhealth_api.packs.generator import Target, generate_pack

    keypool = KeyPool.from_settings(settings, lambda: datetime.now(UTC))
    ai = AIService(GeminiProvider(list(settings.gemini_keys), settings), keypool, settings)
    for tag in tags:
        entry = languages.get(tag)
        if entry is None:
            print(f"{tag}: not in languages.yaml, skipped", file=sys.stderr)
            continue
        target = Target(tag=tag, name_en=entry.name_en, name_native=entry.name_native, entry=entry)
        result = await generate_pack(target, base, ai, request_id=f"gen-packs-{tag}")
        pack = result.pack
        accepted = {k: v for k, v in pack.strings.items() if k not in pack.fallback_keys}
        write_pack(
            build_pack(
                tag, accepted, pack.fallback_keys, base, languages, confidence=pack.confidence
            )
        )
        print(f"{tag}: coverage {pack.coverage}, {len(pack.fallback_keys)} fallback keys")
    keypool.persist()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--rebase", action="store_true")
    group.add_argument("--assemble", nargs=2, metavar=("TAG", "FLAT_JSON"))
    parser.add_argument("--tags", help="comma list for generation (default: every Tier 1+2 tag)")
    args = parser.parse_args(argv)
    base = BasePack.load(LANGPACKS / "en.json")
    languages = LanguageTable.load(DATA_DIR / "languages.yaml", LANGPACKS)
    if args.check:
        return cmd_check(base)
    if args.rebase:
        return cmd_rebase(base, languages)
    if args.assemble:
        return cmd_assemble(args.assemble[0], Path(args.assemble[1]), base, languages)
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    else:
        tags = [
            tag for tag, e in languages.entries.items()
            if tag != "en" and e.tier in (PackTier.tier_1, PackTier.tier_2)
        ]  # fmt: skip
    return asyncio.run(cmd_generate(tags, base, languages))


if __name__ == "__main__":
    raise SystemExit(main())
