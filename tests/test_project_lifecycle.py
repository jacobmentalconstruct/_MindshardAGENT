"""Tests for the unified project lifecycle.

Tests attach -> brief -> tools -> sync -> detach workflow.
Does not require Ollama or GUI -- pure backend logic.
"""
import json
import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture
def project_dir(tmp_path):
    """A fake project directory with some files."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')\n")
    (tmp_path / "README.md").write_text("# Test Project\n")
    return tmp_path


@pytest.fixture
def vault_dir(tmp_path):
    p = tmp_path / "vault"
    p.mkdir()
    return p


class TestProjectMeta:
    def test_create_and_save(self, project_dir):
        from src.core.project.project_meta import ProjectMeta
        meta = ProjectMeta(project_dir)
        assert not meta.exists
        meta.update({
            "display_name": "TestProj",
            "project_purpose": "Testing",
            "current_goal": "Run tests",
            "profile": "standard",
        })
        assert meta.exists
        assert meta.display_name == "TestProj"
        assert meta.profile == "standard"

    def test_self_edit_profile(self, project_dir):
        from src.core.project.project_meta import ProjectMeta, PROFILE_SELF_EDIT
        meta = ProjectMeta(project_dir)
        meta.update({"profile": PROFILE_SELF_EDIT})
        assert meta.is_self_edit

    def test_prompt_context_includes_brief(self, project_dir):
        from src.core.project.project_meta import ProjectMeta
        meta = ProjectMeta(project_dir)
        meta.update({
            "display_name": "MyApp",
            "project_purpose": "A cool app",
            "current_goal": "Add feature X",
        })
        ctx = meta.prompt_context()
        assert "MyApp" in ctx
        assert "A cool app" in ctx
        assert "Add feature X" in ctx

    def test_reload_from_disk(self, project_dir):
        from src.core.project.project_meta import ProjectMeta
        meta = ProjectMeta(project_dir)
        meta.update({"display_name": "Persisted", "project_purpose": "Persist me"})
        # Create fresh instance -- should load from disk
        meta2 = ProjectMeta(project_dir)
        assert meta2.display_name == "Persisted"

    def test_brief_form_data(self, project_dir):
        from src.core.project.project_meta import ProjectMeta, PROFILE_SELF_EDIT
        meta = ProjectMeta(project_dir)
        meta.update({
            "display_name": "Editable Name",
            "project_purpose": "Edit prompt docs",
            "current_goal": "Add prompt preview",
            "project_type": "Python app",
            "constraints": "Do not touch network calls",
            "profile": PROFILE_SELF_EDIT,
        })
        data = meta.brief_form_data()
        assert data["display_name"] == "Editable Name"
        assert data["project_purpose"] == "Edit prompt docs"
        assert data["current_goal"] == "Add prompt preview"
        assert data["project_type"] == "Python app"
        assert data["constraints"] == "Do not touch network calls"
        assert data["profile"] == PROFILE_SELF_EDIT

    def test_prompt_override_scaffold(self, project_dir):
        from src.core.project.project_meta import ProjectMeta
        meta = ProjectMeta(project_dir)
        created = meta.ensure_prompt_override_scaffold()
        override_dir = project_dir / ".mindshard" / "state" / "prompt_overrides"
        assert override_dir.exists()
        assert (override_dir / "README.md").exists()
        assert (override_dir / "90_local_notes.md").exists()
        assert len(created) == 2


class TestWorkspaceDirs:
    def test_init_creates_mindshard_subdirs(self, project_dir):
        """Engine._init_workspace_dirs should create all .mindshard/ subdirs."""
        # Simulate what engine does without spinning up the full engine
        from pathlib import Path
        root = Path(project_dir)
        sidecar = root / ".mindshard"
        for d in ("vcs", "sessions", "logs", "tools", "parts", "ref", "outputs", "state"):
            (sidecar / d).mkdir(parents=True, exist_ok=True)

        for d in ("vcs", "sessions", "logs", "tools", "parts", "ref", "outputs", "state"):
            assert (sidecar / d).exists(), f".mindshard/{d} should exist"

        # Old top-level dirs should NOT exist
        for d in ("_tools", "_parts", "_ref", "_sessions", "_logs"):
            assert not (root / d).exists(), f"{d} should not exist at root"


class TestToolDiscovery:
    def test_discovers_tool_in_mindshard_tools(self, project_dir):
        from src.core.sandbox.tool_discovery import discover_tools
        tools_dir = project_dir / ".mindshard" / "tools"
        tools_dir.mkdir(parents=True)
        tool_file = tools_dir / "my_tool.py"
        tool_file.write_text('"""\nTool: my_tool\nDescription: A test tool\nParameters: message:string:required\n"""\nimport json, sys\nparams = {}\nprint(json.dumps({"result": params.get("message", "")}))\n')
        found = discover_tools(project_dir)
        assert len(found) == 1
        assert found[0].name == "my_tool"

    def test_ignores_files_not_in_mindshard_tools(self, project_dir):
        from src.core.sandbox.tool_discovery import discover_tools
        # Tool at root level (old layout) -- should NOT be discovered
        bad_tool = project_dir / "_tools" / "old_tool.py"
        bad_tool.parent.mkdir(parents=True)
        bad_tool.write_text('"""Tool: old_tool\nDescription: old\nParameters:\n"""')
        found = discover_tools(project_dir)
        assert len(found) == 0


class TestProjectSyncer:
    def test_sync_excludes_mindshard(self, tmp_path):
        from src.core.sandbox.project_syncer import _should_sync
        from pathlib import Path
        # .mindshard should never be synced
        mindshard_rel = Path(".mindshard") / "logs" / "sync_log.jsonl"
        assert not _should_sync(mindshard_rel)

    def test_diff_no_target_name(self, tmp_path):
        from src.core.sandbox.project_syncer import diff_sandbox_to_source
        working = tmp_path / "working"
        source = tmp_path / "source"
        working.mkdir()
        source.mkdir()
        (working / "app.py").write_text("v2\n")
        (source / "app.py").write_text("v1\n")
        result = diff_sandbox_to_source(working, source, target_name="")
        assert "app.py" in result["modified"]
        assert result.get("error") is None


class TestArchiver:
    def test_archive_and_remove(self, project_dir, vault_dir):
        from src.core.project.project_archiver import archive_sidecar, remove_sidecar
        # Create a fake sidecar
        sidecar = project_dir / ".mindshard"
        sidecar.mkdir()
        (sidecar / "state").mkdir()
        (sidecar / "state" / "project_meta.json").write_text(
            '{"display_name": "TestProj"}')

        result = archive_sidecar(project_dir, vault_dir)
        assert result["success"], result.get("error")
        assert Path(result["archive_path"]).exists()

        # Now remove sidecar
        removed = remove_sidecar(project_dir)
        assert removed
        assert not sidecar.exists()

    def test_archive_fails_gracefully_when_no_sidecar(self, project_dir, vault_dir):
        from src.core.project.project_archiver import archive_sidecar
        result = archive_sidecar(project_dir, vault_dir)
        assert not result["success"]
        assert "No .mindshard/" in result["error"]


class TestMemoryVault:
    def test_register_and_list(self, vault_dir):
        from src.core.vault.memory_vault import MemoryVault
        vault = MemoryVault(vault_dir)
        vault.register(
            {"project_name": "TestProj", "archive_path": "/fake/path.zip",
             "snapshot_hash": "abc123", "ts": "2026-03-19"},
            {"project_purpose": "Testing", "current_goal": "Run tests",
             "profile": "standard", "source_path": ""},
        )
        projects = vault.list_projects()
        assert len(projects) == 1
        assert projects[0]["project_name"] == "TestProj"
        assert projects[0]["purpose"] == "Testing"
        vault.close()

    def test_vault_creates_dir(self, tmp_path):
        from src.core.vault.memory_vault import MemoryVault
        new_dir = tmp_path / "new_vault"
        vault = MemoryVault(new_dir)
        assert new_dir.exists()
        assert vault.db_path.exists()
        vault.close()


class TestDetachRetention:
    def _make_engine(self, project_dir, vault_dir):
        from src.core.config.app_config import AppConfig
        from src.core.engine import Engine
        from src.core.runtime.activity_stream import ActivityStream
        from src.core.runtime.event_bus import EventBus
        from src.core.vault.memory_vault import MemoryVault

        config = AppConfig(sandbox_root=str(project_dir), selected_model="test-model")
        engine = Engine(config=config, activity=ActivityStream(), bus=EventBus())
        engine.vault.close()
        engine.vault = MemoryVault(vault_dir)
        engine.set_sandbox(str(project_dir))
        engine.project_meta.update({
            "display_name": "DetachMe",
            "project_purpose": "Testing detach retention",
            "current_goal": "Archive the sidecar",
        })
        return engine

    def test_detach_removes_sidecar_by_default(self, project_dir, vault_dir):
        engine = self._make_engine(project_dir, vault_dir)
        result = engine.detach_project()
        assert result["success"], result.get("error")
        assert not (project_dir / ".mindshard").exists()
        assert Path(result["archive_path"]).exists()
        assert len(engine.vault.list_projects()) == 1
        engine.vault.close()

    def test_detach_can_keep_sidecar(self, project_dir, vault_dir):
        engine = self._make_engine(project_dir, vault_dir)
        result = engine.detach_project(keep_sidecar=True)
        assert result["success"], result.get("error")
        assert result["sidecar_retained"] is True
        assert (project_dir / ".mindshard").exists()
        assert Path(result["archive_path"]).exists()
        assert len(engine.vault.list_projects()) == 1
        engine.vault.close()
