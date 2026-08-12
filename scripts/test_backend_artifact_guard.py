import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("backend_artifact_guard.py")


def write_jar(path: Path, migrations: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as jar:
        for name, content in migrations.items():
            jar.writestr(f"BOOT-INF/classes/db/migration/{name}", content)


class BackendArtifactGuardTest(unittest.TestCase):
    def run_guard(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_identical_migration_manifests_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "current.jar"
            candidate = root / "candidate.jar"
            migrations = {"V1__init.sql": "create table sample(id int);"}
            write_jar(current, migrations)
            write_jar(candidate, migrations)

            result = self.run_guard("compare", "--current-jar", str(current), "--candidate-jar", str(candidate))

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("migration guard passed", result.stdout)

    def test_new_migration_is_rejected_without_explicit_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "current.jar"
            candidate = root / "candidate.jar"
            write_jar(current, {"V1__init.sql": "one"})
            write_jar(candidate, {"V1__init.sql": "one", "V2__extra.sql": "two"})

            result = self.run_guard("compare", "--current-jar", str(current), "--candidate-jar", str(candidate))

            self.assertNotEqual(0, result.returncode)
            self.assertIn("unauthorized new migration", result.stderr)
            self.assertIn("V2__extra.sql", result.stderr)

    def test_changed_applied_migration_is_always_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "current.jar"
            candidate = root / "candidate.jar"
            write_jar(current, {"V1__init.sql": "original"})
            write_jar(candidate, {"V1__init.sql": "changed"})

            result = self.run_guard(
                "compare",
                "--current-jar",
                str(current),
                "--candidate-jar",
                str(candidate),
                "--allow-new-migrations",
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("changed existing migration", result.stderr)

    def test_manifest_round_trip_supports_remote_current_jar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "current.jar"
            candidate = root / "candidate.jar"
            manifest = root / "current.json"
            migrations = {"V1__init.sql": "one", "V2__extra.sql": "two"}
            write_jar(current, migrations)
            write_jar(candidate, migrations)

            emitted = self.run_guard("manifest", "--jar", str(current))
            self.assertEqual(0, emitted.returncode, emitted.stderr)
            manifest.write_text(emitted.stdout)
            self.assertEqual(2, len(json.loads(emitted.stdout)))

            checked = self.run_guard(
                "compare",
                "--current-manifest",
                str(manifest),
                "--candidate-jar",
                str(candidate),
            )
            self.assertEqual(0, checked.returncode, checked.stderr)


class BackendDeployScriptContractTest(unittest.TestCase):
    def test_deployment_has_required_production_safety_gates(self) -> None:
        source = Path(__file__).with_name("deploy-backend-vps.sh").read_text()

        for required in (
            'archive "$COMMIT"',
            "backend_artifact_guard.py",
            "sha256sum",
            "docker cp",
            "rollback",
            "check-first-use",
            "--execute",
        ):
            self.assertIn(required, source)


if __name__ == "__main__":
    unittest.main()
