"""``GET /v1/rules`` + ``RulesRepo`` loading (API_CONTRACT §3.10; BUILD_PLAN §5.4 step 4).

WP2 writes ``data/rules/{deadlines,fixed_notices,clerk_needs}.yaml`` in parallel: while a file is
absent the repo serves the empty shape; once ``deadlines.yaml`` exists it serves its 12 rules.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

from proxyhealth_api.contracts.enums import DocumentType
from proxyhealth_api.contracts.rules import RulesResponse
from proxyhealth_api.resources.rules_repo import RulesLoadError, RulesRepo
from tests.unit._fixtures_wp3 import RULES_DIR

DEADLINES = RULES_DIR / "deadlines.yaml"


async def test_rules_endpoint_serves_the_seeded_table(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/rules")
    assert r.status_code == 200
    body = RulesResponse.model_validate(r.json())
    if not DEADLINES.is_file():  # WP2 has not landed deadlines.yaml yet
        assert body.rules == [] and body.rules_version == "0"
        return
    data = yaml.safe_load(DEADLINES.read_text(encoding="utf-8"))
    assert len(body.rules) == len(data["rules"]) == 12
    assert body.rules_version == str(data["rules_version"])
    assert [rule.id for rule in body.rules][:2] == ["ar11_10d", "bia_appeal_30d"]
    assert len({rule.id for rule in body.rules}) == 12


def test_missing_files_give_empty_collections(tmp_path: Path) -> None:
    repo = RulesRepo.load(tmp_path)
    assert repo.deadline_rules() == []
    assert repo.version == "0"
    assert repo.fixed_notices(DocumentType.jury_summons) == []
    assert repo.clerk_need(DocumentType.jury_summons) == ""
    assert repo.prepare_items(DocumentType.jury_summons) == []


def test_real_rules_dir_loads_every_present_file() -> None:
    repo = RulesRepo.load(RULES_DIR)
    assert repo.prepare_items(DocumentType.jury_summons) == ["bring_the_summons"]
    if (RULES_DIR / "fixed_notices.yaml").is_file():
        notices = repo.fixed_notices(DocumentType.jury_summons)
        assert notices and all(n.fixed_copy_key.startswith("fixed.") for n in notices)
    if (RULES_DIR / "clerk_needs.yaml").is_file():
        need = repo.clerk_need(DocumentType.uscis_receipt)
        assert 0 < len(need) <= 200


def test_invalid_deadlines_file_names_path_and_line(tmp_path: Path) -> None:
    path = tmp_path / "deadlines.yaml"
    path.write_text(
        'rules_version: "x"\nrules:\n  - id: only_an_id\n    days: ten\n', encoding="utf-8"
    )
    with pytest.raises(RulesLoadError) as err:
        RulesRepo.load(tmp_path)
    assert str(err.value).startswith(f"{path}:3:")


def test_duplicate_rule_id_refuses(tmp_path: Path) -> None:
    data = yaml.safe_load(DEADLINES.read_text(encoding="utf-8")) if DEADLINES.is_file() else None
    if data is None:
        pytest.skip("deadlines.yaml not written yet (WP2)")
    data["rules"].append(dict(data["rules"][0]))
    (tmp_path / "deadlines.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(RulesLoadError, match="duplicate rule id"):
        RulesRepo.load(tmp_path)


def test_fixed_notice_needs_fixed_prefix(tmp_path: Path) -> None:
    (tmp_path / "fixed_notices.yaml").write_text(
        "notices:\n  - id: x\n    document_types: [jury_summons]\n"
        "    kind: jury_citizenship_warning\n    severity: high\n"
        "    fixed_copy_key: jury_summons\n",
        encoding="utf-8",
    )
    with pytest.raises(RulesLoadError, match="fixed."):
        RulesRepo.load(tmp_path)
