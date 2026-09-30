"""K-19 / T-22: startup and deploy scripts never report success after a failure.

deploy.sh is executed for real against stub git/docker/curl commands (nothing
touches a real repository, Docker or server). The PowerShell scripts cannot
run in Linux CI, so their structure is checked statically.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

STUB = """#!/usr/bin/env bash
echo "$(basename "$0") $*" >> "$STUB_LOG"
case "$(basename "$0") $*" in
  *"$FAIL_ON"*) exit 17 ;;
esac
if [ "$(basename "$0")" = "curl" ]; then
  echo "$HEALTH_BODY"
fi
exit 0
"""


class DeployShTest(unittest.TestCase):
    def _run(self, fail_on: str = "__never__", health: str = '{"status":"ok"}'):
        work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work, ignore_errors=True)
        (work / "scripts").mkdir()
        shutil.copy(SCRIPTS / "deploy.sh", work / "scripts" / "deploy.sh")
        bin_dir = work / "bin"
        bin_dir.mkdir()
        for name in ("git", "docker", "curl", "sleep"):
            path = bin_dir / name
            path.write_text(STUB, encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        log = work / "calls.log"
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "STUB_LOG": str(log),
            "FAIL_ON": fail_on,
            "HEALTH_BODY": health,
        }
        result = subprocess.run(
            ["bash", str(work / "scripts" / "deploy.sh")],
            env=env, capture_output=True, text=True, timeout=60,
        )
        calls = log.read_text(encoding="utf-8") if log.exists() else ""
        return result, calls

    def test_success_path_migrates_before_restart_and_waits_for_health(self):
        result, calls = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Deploy complete", result.stdout)
        lines = calls.splitlines()
        migrate = next(i for i, c in enumerate(lines) if "alembic upgrade head" in c)
        restart = next(i for i, c in enumerate(lines) if c.startswith("docker compose up"))
        health = next(i for i, c in enumerate(lines) if c.startswith("curl"))
        self.assertLess(migrate, restart)
        self.assertLess(restart, health)

    def test_failed_build_stops_before_anything_else(self):
        result, calls = self._run(fail_on="docker compose build")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Deploy complete", result.stdout)
        self.assertNotIn("alembic", calls)
        self.assertNotIn("compose up", calls)

    def test_failed_migration_is_not_masked(self):
        result, calls = self._run(fail_on="alembic upgrade head")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Deploy complete", result.stdout)
        self.assertNotIn("compose up", calls)

    def test_degraded_health_fails_the_deploy(self):
        result, _calls = self._run(health='{"status":"degraded","migrations":"pending"}')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Deploy complete", result.stdout)
        self.assertIn("did not become healthy", result.stderr)


NATIVE = re.compile(r"^\s*(git|docker)\s")


class PowerShellScriptsTest(unittest.TestCase):
    def _lines(self, name: str) -> list[str]:
        return (SCRIPTS / name).read_text(encoding="utf-8").splitlines()

    def test_every_native_command_is_exit_code_checked(self):
        for name in ("deploy.ps1", "start-dev.ps1"):
            unchecked = [
                line.strip()
                for line in self._lines(name)
                if NATIVE.match(line) and line.strip() != "docker compose ps"
            ]
            self.assertEqual(unchecked, [], f"{name}: native calls outside Invoke-Native")
            self.assertIn("$LASTEXITCODE -ne 0", "\n".join(self._lines(name)))

    def test_migrations_run_before_success_is_announced(self):
        for name, success in (("deploy.ps1", "Deploy complete"), ("start-dev.ps1", "Opening app")):
            text = "\n".join(self._lines(name))
            migrate = text.index("alembic upgrade head")
            self.assertLess(migrate, text.index(success), name)
            self.assertLess(migrate, text.rindex("up -d"), name)

    def test_readiness_requires_healthy_status_not_just_http(self):
        start_dev = "\n".join(self._lines("start-dev.ps1"))
        self.assertIn("-RequireHealthyJson", start_dev)
        self.assertIn('$body.status -eq "ok"', start_dev)
        deploy = "\n".join(self._lines("deploy.ps1"))
        self.assertIn("Wait-ForHealthy", deploy)
        self.assertLess(deploy.rindex("Wait-ForHealthy"), deploy.index("Deploy complete"))


if __name__ == "__main__":
    unittest.main()
