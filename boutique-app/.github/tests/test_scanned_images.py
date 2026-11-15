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


class ScannedImagesTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        for service in SERVICES:
            self.write_record(service)

    def write_record(self, service, revision=REVISION, digest=DIGEST):
        directory = self.path / f"scanned-image-{service}"
        directory.mkdir(exist_ok=True)
        (directory / f"{service}.json").write_text(
            json.dumps({"revision": revision, "digest": digest}), encoding="utf-8"
        )

    def run_manifest(self, mode="dev"):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.path), "test-owner", REVISION, mode],
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

    def test_preview_omits_load_generator(self):
        result = self.run_manifest("preview")
        self.assertEqual(result.returncode, 0, result.stderr)
        images = json.loads(result.stdout)["images"]
        self.assertEqual(len(images), len(SERVICES) - 1)
        self.assertFalse(any("/loadgenerator" in image for image in images))

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
