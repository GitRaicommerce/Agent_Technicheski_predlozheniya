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
action_execution_record = manifest_actions_module.action_execution_record
action_execution_summary = manifest_actions_module.action_execution_summary
action_url = manifest_actions_module.action_url
execute_action = manifest_actions_module.execute_action
job_result_from_action_response = manifest_actions_module.job_result_from_action_response
job_status_url = manifest_actions_module.job_status_url
load_manifest = manifest_actions_module.load_manifest
main = manifest_actions_module.main
manifest_actions = manifest_actions_module.manifest_actions
render_execution_report_json = manifest_actions_module.render_execution_report_json
render_execution_report_markdown = manifest_actions_module.render_execution_report_markdown
request_target_summary = manifest_actions_module.request_target_summary
select_actions = manifest_actions_module.select_actions
wait_for_job_result = manifest_actions_module.wait_for_job_result


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

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

    def test_manifest_actions_synthesize_dispatcher_path_for_legacy_readiness_rows(self):
        manifest = {
            "readiness_actions": [
                {
                    "action_key": "resolve_duplicate_selected",
                    "blocker_code": "duplicate_selected",
                    "section_count": 14,
                }
            ]
        }

        actions = manifest_actions(manifest)

        self.assertEqual(len(actions), 1)
        self.assertEqual(
            actions[0].api_path,
            "/api/v1/agents/{project_id}/remediation-actions/resolve_duplicate_selected",
        )
        self.assertEqual(actions[0].api_method, "POST")

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

    def test_job_result_from_action_response_reads_generation_job(self):
        result = {
            "status_code": 200,
            "body": {
                "action_key": "regenerate_stale",
                "status": "queued",
                "result": {
                    "id": "job-1",
                    "project_id": "project-1",
                    "status": "queued",
                },
            },
        }

        self.assertEqual(
            job_result_from_action_response(result),
            {"id": "job-1", "project_id": "project-1", "status": "queued"},
        )
        self.assertIsNone(job_result_from_action_response({"body": {"result": {}}}))

    def test_job_status_url_quotes_project_and_job_ids(self):
        self.assertEqual(
            job_status_url("http://localhost:8000", "project 1", "job/1"),
            "http://localhost:8000/api/v1/agents/project%201/generation-jobs/job%2F1",
        )

    def test_request_target_summary_lists_section_uids_and_title_hints(self):
        self.assertEqual(
            request_target_summary(
                {
                    "section_uids": ["sec-quality", "sec-risk"],
                    "section_title_hints": ["Quality controls"],
                }
            ),
            "uids=sec-quality, sec-risk; titles=Quality controls",
        )
        self.assertEqual(request_target_summary({}), "")

    def test_wait_for_job_result_polls_until_terminal_status(self):
        opener = Mock(
            side_effect=[
                FakeResponse(
                    {
                        "id": "job-1",
                        "project_id": "project-1",
                        "status": "processing",
                    }
                ),
                FakeResponse(
                    {
                        "id": "job-1",
                        "project_id": "project-1",
                        "status": "done",
                    }
                ),
            ]
        )
        sleeper = Mock()
        ticks = iter([0.0, 1.0])

        result = wait_for_job_result(
            {
                "body": {
                    "result": {
                        "id": "job-1",
                        "project_id": "project-1",
                    }
                }
            },
            api_base="http://localhost:8000",
            project_id=None,
            timeout=10,
            poll_interval=0.5,
            opener=opener,
            sleeper=sleeper,
            monotonic=lambda: next(ticks),
        )

        self.assertEqual(result["body"]["status"], "done")
        self.assertEqual(opener.call_count, 2)
        self.assertEqual(sleeper.call_args.args[0], 0.5)
        request = opener.call_args_list[0].args[0]
        self.assertEqual(request.get_method(), "GET")

    def test_wait_for_job_result_returns_none_for_non_job_actions(self):
        self.assertIsNone(
            wait_for_job_result(
                {"body": {"status": "resolved"}},
                api_base="http://localhost:8000",
                project_id="project-1",
                timeout=10,
                poll_interval=0,
                opener=Mock(),
                sleeper=Mock(),
            )
        )

    def test_action_execution_reports_planned_and_waited_statuses(self):
        action = ManifestAction(
            action_key="regenerate_stale",
            api_method="POST",
            api_path="/api/v1/example",
            source="readiness_actions",
            section_count=2,
            summary="Section A | Section B",
            request_json={
                "section_uids": ["sec-a"],
                "section_title_hints": ["Section A"],
            },
        )
        planned = action_execution_record(
            action,
            url="http://localhost/api/v1/example",
            executed=False,
        )
        waited = action_execution_record(
            action,
            url="http://localhost/api/v1/example",
            executed=True,
            action_result={"status_code": 200, "body": {"status": "queued"}},
            wait_result={"status_code": 200, "body": {"status": "done"}},
        )

        payload = json.loads(render_execution_report_json([planned, waited]))
        markdown = render_execution_report_markdown([planned, waited])

        self.assertEqual(
            payload["schema_version"],
            "calibration_action_execution.v1",
        )
        self.assertEqual(payload["total_actions"], 2)
        self.assertEqual(payload["executed_actions"], 1)
        self.assertEqual(payload["status_counts"], {"planned": 1, "done": 1})
        self.assertFalse(payload["ready_for_bundle"])
        self.assertTrue(payload["has_unexecuted_actions"])
        self.assertEqual(payload["actions"][1]["final_status"], "done")
        self.assertEqual(
            payload["actions"][0]["target_summary"],
            "uids=sec-a; titles=Section A",
        )
        self.assertIn("Ready for calibration bundle: `no`", markdown)
        self.assertIn("Has unexecuted actions: `yes`", markdown)
        self.assertIn(
            "| regenerate_stale | readiness_actions | no | planned | 2 | "
            "uids=sec-a; titles=Section A |",
            markdown,
        )
        self.assertIn("Section A \\| Section B", markdown)

    def test_action_execution_summary_marks_successful_waited_actions_ready(self):
        action = ManifestAction(
            action_key="regenerate_stale",
            api_method="POST",
            api_path="/api/v1/example",
        )
        record = action_execution_record(
            action,
            url="http://localhost/api/v1/example",
            executed=True,
            action_result={"status_code": 200, "body": {"status": "queued"}},
            wait_result={"status_code": 200, "body": {"status": "done"}},
        )

        summary = action_execution_summary([record])

        self.assertEqual(summary["executed_actions"], 1)
        self.assertEqual(summary["status_counts"], {"done": 1})
        self.assertFalse(summary["has_failures"])
        self.assertFalse(summary["has_unexecuted_actions"])
        self.assertTrue(summary["ready_for_bundle"])

    def test_action_execution_summary_blocks_failed_actions(self):
        action = ManifestAction(
            action_key="regenerate_stale",
            api_method="POST",
            api_path="/api/v1/example",
        )
        record = action_execution_record(
            action,
            url="http://localhost/api/v1/example",
            executed=True,
            action_result={"status_code": 200, "body": {"status": "queued"}},
            wait_result={"status_code": 200, "body": {"status": "error"}},
        )

        summary = action_execution_summary([record])

        self.assertEqual(summary["failure_statuses"], ["error"])
        self.assertTrue(summary["has_failures"])
        self.assertFalse(summary["ready_for_bundle"])

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

    def test_main_wait_returns_error_when_generation_job_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "calibration_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "project_id": "project-1",
                        "readiness_actions": [
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
            out_json = Path(tmp) / "execution.json"
            out_md = Path(tmp) / "execution.md"
            original_execute = manifest_actions_module.execute_action
            original_wait = manifest_actions_module.wait_for_job_result
            manifest_actions_module.execute_action = Mock(
                return_value={
                    "status_code": 200,
                    "body": {"result": {"id": "job-1", "project_id": "project-1"}},
                }
            )
            manifest_actions_module.wait_for_job_result = Mock(
                return_value={
                    "status_code": 200,
                    "body": {"id": "job-1", "status": "error"},
                }
            )
            try:
                self.assertEqual(
                    main(
                        [
                            "--manifest",
                            str(manifest_path),
                            "--execute",
                            "--wait",
                            "--action-key",
                            "regenerate_stale",
                            "--out-json",
                            str(out_json),
                            "--out-md",
                            str(out_md),
                        ]
                    ),
                    1,
                )
                report = json.loads(out_json.read_text(encoding="utf-8"))
                self.assertEqual(report["status_counts"], {"error": 1})
                self.assertEqual(report["actions"][0]["final_status"], "error")
                self.assertIn(
                    "Calibration action execution report",
                    out_md.read_text(encoding="utf-8"),
                )
            finally:
                manifest_actions_module.execute_action = original_execute
                manifest_actions_module.wait_for_job_result = original_wait

    def test_load_manifest_rejects_non_object_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "calibration_manifest.json"
            manifest_path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object"):
                load_manifest(manifest_path)


if __name__ == "__main__":
    unittest.main()
