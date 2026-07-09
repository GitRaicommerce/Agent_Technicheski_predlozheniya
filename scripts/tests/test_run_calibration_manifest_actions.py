from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_calibration_manifest_actions.py"
spec = importlib.util.spec_from_file_location("manifest_actions", SCRIPT)
manifest_actions_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = manifest_actions_module
spec.loader.exec_module(manifest_actions_module)

ManifestAction = manifest_actions_module.ManifestAction
action_url = manifest_actions_module.action_url
execute_action = manifest_actions_module.execute_action
load_manifest = manifest_actions_module.load_manifest
main = manifest_actions_module.main
manifest_actions = manifest_actions_module.manifest_actions
select_actions = manifest_actions_module.select_actions


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class CalibrationManifestActionTests(unittest.TestCase):
    def test_manifest_actions_require_action_key_and_api_path(self):
        manifest = {
            "readiness_actions": [
                {
                    "action_key": "regenerate_stale",
                    "api_method": "POST",
                    "api_path": "/api/v1/agents/project-1/remediation-actions/regenerate_stale",
                    "blocker_code": "stale_evidence",
                    "section_count": 2,
                    "summary": "Section A, Section B",
                }
            ]
        }

        actions = manifest_actions(manifest)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_key, "regenerate_stale")
        self.assertEqual(actions[0].api_method, "POST")
        self.assertEqual(actions[0].source, "readiness_actions")
        self.assertEqual(actions[0].section_count, 2)

    def test_manifest_actions_include_executable_gap_rows_without_duplicates(self):
        manifest = {
            "readiness_actions": [
                {
                    "action_key": "regenerate_quality_depth",
                    "api_method": "POST",
                    "api_path": "/api/v1/agents/project-1/remediation-actions/regenerate_quality_depth",
                    "section_count": 3,
                }
            ],
            "gap_priority_rows": [
                {
                    "focus": "drafting depth",
                    "reference_section": "Quality",
                    "action_key": "regenerate_quality_depth",
                    "api_method": "POST",
                    "api_path": "/api/v1/agents/project-1/remediation-actions/regenerate_quality_depth",
                },
                {
                    "focus": "grounding and checklist coverage",
                    "reference_section": "Environment",
                    "request_json": {
                        "section_title_hints": ["Environmental protection"]
                    },
                    "action_key": "regenerate_missing_requirements",
                    "api_method": "POST",
                    "api_path": "/api/v1/agents/project-1/remediation-actions/regenerate_missing_requirements",
                },
                {
                    "focus": "outline mapping",
                    "reference_section": "Organization",
                    "ui_action": "Review outline mapping",
                },
            ],
        }

        actions = manifest_actions(manifest)

        self.assertEqual(
            [action.action_key for action in actions],
            ["regenerate_quality_depth", "regenerate_missing_requirements"],
        )
        self.assertEqual(actions[0].source, "readiness_actions")
        self.assertEqual(actions[0].section_count, 3)
        self.assertEqual(actions[1].source, "gap_priority_rows")
        self.assertEqual(actions[1].section_count, 1)
        self.assertEqual(
            actions[1].request_json,
            {"section_title_hints": ["Environmental protection"]},
        )
        self.assertEqual(
            actions[1].summary,
            "gap=grounding and checklist coverage, reference=Environment",
        )

    def test_action_url_substitutes_project_id_template(self):
        url = action_url(
            "http://localhost:8000",
            "/api/v1/agents/{project_id}/remediation-actions/regenerate_stale",
            "project 1",
        )

        self.assertEqual(
            url,
            "http://localhost:8000/api/v1/agents/project%201/remediation-actions/regenerate_stale",
        )

    def test_select_actions_rejects_missing_action_key(self):
        actions = [
            ManifestAction(
                action_key="regenerate_stale",
                api_method="POST",
                api_path="/api/v1/example",
            )
        ]

        with self.assertRaisesRegex(ValueError, "not found"):
            select_actions(
                actions,
                action_keys=["regenerate_missing_requirements"],
                all_actions=False,
            )

    def test_execute_action_posts_json_request(self):
        opener = Mock(return_value=FakeResponse({"status": "queued"}))
        action = ManifestAction(
            action_key="regenerate_stale",
            api_method="POST",
            api_path="/api/v1/example",
            request_json={"section_title_hints": ["Quality"]},
        )

        result = execute_action(
            action,
            url="http://localhost:8000/api/v1/example",
            timeout=5,
            opener=opener,
        )

        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["body"]["status"], "queued")
        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"section_title_hints": ["Quality"]},
        )

    def test_main_refuses_execute_without_explicit_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "calibration_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "project_id": "project-1",
                        "gap_priority_rows": [
                            {
                                "action_key": "regenerate_stale",
                                "api_method": "POST",
                                "api_path": "/api/v1/agents/project-1/remediation-actions/regenerate_stale",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                main(["--manifest", str(manifest_path), "--execute"]),
                1,
            )

    def test_load_manifest_rejects_non_object_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "calibration_manifest.json"
            manifest_path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object"):
                load_manifest(manifest_path)


if __name__ == "__main__":
    unittest.main()
