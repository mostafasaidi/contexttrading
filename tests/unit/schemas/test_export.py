"""Tests for schemas.export: versioned JSON schema artifacts."""

from __future__ import annotations

import json

from contexttrading import __version__
from contexttrading.models.candle import Candle
from contexttrading.schemas.export import (
    EXPORTED_MODELS,
    default_output_dir,
    export_schemas,
    main,
    model_schema_document,
)


class TestExport:
    def test_exports_all_models(self, tmp_path) -> None:
        written = export_schemas(tmp_path)
        assert len(written) == len(EXPORTED_MODELS)
        names = {p.name for p in written}
        assert "Candle-v1.json" in names
        assert "AnalysisResult-v1.json" in names
        assert "VisualStyle-v1.json" in names

    def test_document_shape(self) -> None:
        document = model_schema_document(Candle)
        assert document["name"] == "Candle"
        assert document["schema_version"] == "1.0.0"
        assert document["engine_version"] == __version__
        schema = document["json_schema"]
        assert "properties" in schema
        assert "timestamp" in schema["properties"]

    def test_written_files_are_valid_json(self, tmp_path) -> None:
        for path in export_schemas(tmp_path):
            document = json.loads(path.read_text(encoding="utf-8"))
            assert document["json_schema"]["title"]

    def test_export_is_deterministic(self, tmp_path) -> None:
        first = {p.name: p.read_text(encoding="utf-8") for p in export_schemas(tmp_path / "a")}
        second = {p.name: p.read_text(encoding="utf-8") for p in export_schemas(tmp_path / "b")}
        assert first == second

    def test_main_cli(self, tmp_path, capsys) -> None:
        assert main(["--out", str(tmp_path)]) == 0
        assert "wrote" in capsys.readouterr().out

    def test_default_output_dir_points_into_repo(self) -> None:
        path = default_output_dir()
        assert path.name == "json"
        assert path.parent.name == "schemas"
