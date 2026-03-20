"""Tests for externalized prompt source loading and precedence."""

from pathlib import Path

from src.core.agent.prompt_sources import load_prompt_sources


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_global_docs_load_in_filename_order(tmp_path):
    global_dir = tmp_path / "global_prompt"
    _write(global_dir / "40_response_style.md", "style")
    _write(global_dir / "00_identity.md", "identity")
    _write(global_dir / "20_intent_interpretation.md", "intent")

    result = load_prompt_sources(global_prompt_dir=global_dir)

    assert [section.name for section in result.sections] == [
        "00_identity.md",
        "20_intent_interpretation.md",
        "40_response_style.md",
    ]
    assert result.text == "identity\n\nintent\n\nstyle"


def test_same_name_override_replaces_global_doc(tmp_path):
    global_dir = tmp_path / "global_prompt"
    override_dir = tmp_path / "override_prompt"
    _write(global_dir / "00_identity.md", "global identity")
    _write(global_dir / "40_response_style.md", "global style")
    _write(override_dir / "40_response_style.md", "project style")

    result = load_prompt_sources(global_prompt_dir=global_dir, override_dir=override_dir)

    assert [section.layer for section in result.sections] == ["global_doc", "project_override"]
    assert "project style" in result.text
    assert "global style" not in result.text


def test_extra_override_file_appends_after_global_set(tmp_path):
    global_dir = tmp_path / "global_prompt"
    override_dir = tmp_path / "override_prompt"
    _write(global_dir / "00_identity.md", "identity")
    _write(global_dir / "40_response_style.md", "style")
    _write(override_dir / "95_project_appendix.md", "appendix")

    result = load_prompt_sources(global_prompt_dir=global_dir, override_dir=override_dir)

    assert [section.name for section in result.sections] == [
        "00_identity.md",
        "40_response_style.md",
        "95_project_appendix.md",
    ]
    assert result.text.endswith("appendix")


def test_missing_global_dir_warns_without_failing(tmp_path):
    missing_dir = tmp_path / "does_not_exist"
    result = load_prompt_sources(global_prompt_dir=missing_dir)
    assert result.sections == ()
    assert result.text == ""
    assert result.warnings
    assert "missing" in result.warnings[0].lower()


def test_fingerprint_changes_when_docs_change(tmp_path):
    global_dir = tmp_path / "global_prompt"
    path = global_dir / "00_identity.md"
    _write(path, "first")
    first = load_prompt_sources(global_prompt_dir=global_dir)

    _write(path, "second")
    second = load_prompt_sources(global_prompt_dir=global_dir)

    assert first.fingerprint != second.fingerprint
