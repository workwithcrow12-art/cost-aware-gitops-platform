import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scanned-images.py"
SERVICES = (
    "adservice", "cartservice", "checkoutservice", "currencyservice", "emailservice",
    "frontend", "loadgenerator", "paymentservice", "productcatalogservice",
    "recommendationservice", "shippingservice",
)
REVISION = "a" * 40
DIGEST = "sha256:" + "b" * 64
FINOPS_DIGEST = "sha256:" + "c" * 64


class ScannedImagesTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "records"
        self.path.mkdir()
        for service in SERVICES:
            self.write_record(service)

    def write_record(self, service, revision=REVISION, digest=DIGEST):
        directory = self.path / f"scanned-image-{service}"
        directory.mkdir(exist_ok=True)
        (directory / f"{service}.json").write_text(
            json.dumps({"revision": revision, "digest": digest}), encoding="utf-8"
        )

    def create_gitops_fixture(self) -> Path:
        gitops = self.root / "gitops-config"
        for env in ("dev", "staging", "prod", "preview"):
            overlay_dir = gitops / "apps" / "boutique" / "overlays" / env
            overlay_dir.mkdir(parents=True, exist_ok=True)
            extra = ""
            if env in ("dev", "staging"):
                extra = "components:\n  - ../../components/loadgenerator\n  - ../../components/restricted\n"
            elif env == "prod":
                extra = (
                    "components:\n  - ../../components/restricted\n"
                    "patches:\n  - path: patch-resources.yaml\n"
                    "    target:\n      kind: Rollout\n      name: frontend\n"
                )
            else:
                extra = (
                    "components:\n  - ../../components/restricted\n"
                    "patches:\n  - patch: |\n      apiVersion: apps/v1\n      kind: Deployment\n"
                )
            (overlay_dir / "kustomization.yaml").write_text(
                f"apiVersion: kustomize.config.k8s.io/v1beta1\n"
                f"kind: Kustomization\n"
                f"namespace: boutique-{env}\n"
                f"resources:\n  - ../../base\n"
                f"{extra}"
                f"labels:\n  - pairs:\n      team: boutique\n      env: {env}\n    includeTemplates: true\n",
                encoding="utf-8",
                newline="\n",
            )
        finops_dir = gitops / "platform" / "finops-reporter"
        finops_dir.mkdir(parents=True, exist_ok=True)
        (finops_dir / "cronjob.yaml").write_text(
            "apiVersion: batch/v1\n"
            "kind: CronJob\n"
            "metadata:\n"
            "  name: finops-reporter\n"
            "spec:\n"
            "  jobTemplate:\n"
            "    spec:\n"
            "      template:\n"
            "        spec:\n"
            "          containers:\n"
            "            - name: reporter\n"
            "              image: ghcr.io/workwithcrow12-art/finops-toolkit:v0.9\n",
            encoding="utf-8",
            newline="\n",
        )
        return gitops

    def run_manifest(self, mode="dev", extra_args=()):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.path), "test-owner", REVISION, mode, *extra_args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_complete_scanned_set_produces_digest_only_replacements(self):
        result = self.run_manifest()
        self.assertEqual(result.returncode, 0, result.stderr)
        images = json.loads(result.stdout)["images"]
        self.assertEqual(len(images), len(SERVICES))
        self.assertIn(
            "us-central1-docker.pkg.dev/online-boutique-ci/microservices-demo/frontend"
            f"=ghcr.io/test-owner/frontend@{DIGEST}", images,
        )

    def test_staging_includes_load_generator(self):
        result = self.run_manifest("staging")
        self.assertEqual(result.returncode, 0, result.stderr)
        images = json.loads(result.stdout)["images"]
        self.assertEqual(len(images), len(SERVICES))
        self.assertTrue(any("/loadgenerator=" in image for image in images))

    def test_prod_and_preview_omit_load_generator(self):
        for env in ("prod", "preview"):
            with self.subTest(env=env):
                result = self.run_manifest(env)
                self.assertEqual(result.returncode, 0, result.stderr)
                images = json.loads(result.stdout)["images"]
                self.assertEqual(len(images), len(SERVICES) - 1)
                self.assertFalse(any("/loadgenerator" in image for image in images))

    def test_apply_gitops_updates_overlays_idempotently_and_preserves_sections(self):
        gitops = self.create_gitops_fixture()
        for env, expected_count in (("dev", 11), ("staging", 11), ("prod", 10), ("preview", 10)):
            with self.subTest(env=env):
                first = self.run_manifest(env, ["--apply-gitops", str(gitops)])
                self.assertEqual(first.returncode, 0, first.stderr)
                kustomization = gitops / "apps" / "boutique" / "overlays" / env / "kustomization.yaml"
                first_text = kustomization.read_text(encoding="utf-8")
                self.assertIn("resources:\n  - ../../base\n", first_text)
                self.assertIn(f"      env: {env}\n", first_text)
                self.assertEqual(first_text.count("newName: ghcr.io/test-owner/"), expected_count)
                if env in ("dev", "staging"):
                    self.assertIn("newName: ghcr.io/test-owner/loadgenerator", first_text)
                else:
                    self.assertNotIn("loadgenerator", first_text)
                    self.assertIn("patches:\n", first_text)

                second = self.run_manifest(env, ["--apply-gitops", str(gitops)])
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(kustomization.read_text(encoding="utf-8"), first_text)

    def test_apply_gitops_replaces_in_middle_images_block_without_clobbering_patches(self):
        gitops = self.create_gitops_fixture()
        prod_kustomization = gitops / "apps" / "boutique" / "overlays" / "prod" / "kustomization.yaml"
        prod_kustomization.write_text(
            "apiVersion: kustomize.config.k8s.io/v1beta1\n"
            "kind: Kustomization\n"
            "namespace: boutique-prod\n"
            "images:\n"
            "  - name: us-central1-docker.pkg.dev/online-boutique-ci/microservices-demo/frontend\n"
            "    newName: ghcr.io/old-owner/frontend\n"
            f"    digest: sha256:{'1' * 64}\n"
            "patches:\n"
            "  - path: patch-resources.yaml\n",
            encoding="utf-8",
            newline="\n",
        )
        result = self.run_manifest("prod", ["--apply-gitops", str(gitops)])
        self.assertEqual(result.returncode, 0, result.stderr)
        updated = prod_kustomization.read_text(encoding="utf-8")
        self.assertNotIn("old-owner", updated)
        self.assertEqual(updated.count("newName: ghcr.io/test-owner/"), 10)
        self.assertTrue(updated.endswith("patches:\n  - path: patch-resources.yaml\n"))

    def test_finops_record_updates_cronjob_and_accepts_release_yml_fields(self):
        gitops = self.create_gitops_fixture()
        finops_record = self.root / "finops-toolkit.json"
        finops_record.write_text(
            json.dumps(
                {
                    "revision": REVISION,
                    "tag": "v0.9",
                    "digest": FINOPS_DIGEST,
                    "image": f"ghcr.io/test-owner/finops-toolkit@{FINOPS_DIGEST}",
                }
            ),
            encoding="utf-8",
        )
        result = self.run_manifest(
            "dev",
            ["--apply-gitops", str(gitops), "--finops-record", str(finops_record)],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        cronjob_text = (gitops / "platform" / "finops-reporter" / "cronjob.yaml").read_text(encoding="utf-8")
        self.assertIn(f"image: ghcr.io/test-owner/finops-toolkit@{FINOPS_DIGEST}", cronjob_text)

        # Idempotent re-run when cronjob already pins a @sha256 digest
        second = self.run_manifest(
            "dev",
            ["--apply-gitops", str(gitops), "--finops-record", str(finops_record)],
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(
            (gitops / "platform" / "finops-reporter" / "cronjob.yaml").read_text(encoding="utf-8"),
            cronjob_text,
        )

    def test_rejects_invalid_finops_record_without_modifying_overlays(self):
        gitops = self.create_gitops_fixture()
        dev_path = gitops / "apps" / "boutique" / "overlays" / "dev" / "kustomization.yaml"
        before = dev_path.read_text(encoding="utf-8")

        bad_record = self.root / "bad-finops.json"
        for payload in (
            {"revision": "f" * 40, "digest": FINOPS_DIGEST},
            {"revision": REVISION, "digest": "v0.9"},
            {"revision": REVISION, "digest": FINOPS_DIGEST, "unexpected": "field"},
        ):
            bad_record.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_manifest(
                "dev",
                ["--apply-gitops", str(gitops), "--finops-record", str(bad_record)],
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(dev_path.read_text(encoding="utf-8"), before)

    def test_finops_record_requires_apply_gitops(self):
        finops_record = self.root / "finops-toolkit.json"
        finops_record.write_text(
            json.dumps({"revision": REVISION, "digest": FINOPS_DIGEST}),
            encoding="utf-8",
        )
        result = self.run_manifest("dev", ["--finops-record", str(finops_record)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--finops-record requires --apply-gitops", result.stderr)

    def test_rejects_missing_service(self):
        directory = self.path / "scanned-image-frontend"
        (directory / "frontend.json").unlink()
        directory.rmdir()
        self.assertIn("complete service set", self.run_manifest().stderr)

    def test_rejects_unexpected_artifact_even_with_a_valid_service_file(self):
        directory = self.path / "scanned-image-extra"
        directory.mkdir()
        (directory / "frontend.json").write_text(
            json.dumps({"revision": REVISION, "digest": DIGEST}), encoding="utf-8"
        )
        self.assertIn("complete service set", self.run_manifest().stderr)

    def test_rejects_wrong_revision(self):
        self.write_record("frontend", revision="b" * 40)
        self.assertIn("frontend.json", self.run_manifest().stderr)

    def test_rejects_non_digest_reference(self):
        self.write_record("frontend", digest="latest")
        self.assertIn("frontend.json", self.run_manifest().stderr)
