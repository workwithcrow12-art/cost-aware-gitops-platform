import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class BootstrapTests(unittest.TestCase):
    def test_explicit_context_and_eks_discovery(self):
        bash = shutil.which("bash")
        if os.name == "nt":
            bash = "C:/Program Files/Git/bin/bash.exe"
        self.assertTrue(bash and Path(bash).exists(), "Bash is required for bootstrap tests")
        source = Path(__file__).resolve().parents[1] / "scripts/bootstrap-argocd.sh"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copyfile(source, scripts / source.name)
            (scripts / "get-kubeconfig.sh").write_text(
                '#!/usr/bin/env bash\necho discovery >> "$CALL_LOG"\necho eks-test\n',
                encoding="utf-8",
            )
            gitops = root / "gitops"
            for name in ("bootstrap/root-app.yaml", "bootstrap/projects/bootstrap.yaml",
                         "platform/argocd/values.yaml"):
                path = gitops / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test: fixture\n", encoding="utf-8")
            for name in ("helm", "kubectl"):
                path = root / name
                path.write_text(
                    '#!/usr/bin/env bash\n'
                    f'printf "{name}|%s\\n" "$*" >> "$CALL_LOG"\n'
                    'if [[ "$*" == *"-f -" ]]; then cat >/dev/null; fi\n', encoding="utf-8",
                )
                path.chmod(0o755)
            log = root / "calls.log"
            environment = dict(os.environ, CALL_LOG=log.as_posix())
            mock_path = root.as_posix()
            if os.name == "nt":
                mock_path = f"/{mock_path[0].lower()}{mock_path[2:]}"
            for args, discovery, context, root_path in (
                (["explicit-eks"], False, "explicit-eks", "gitops-config/bootstrap/nonprod"),
                (["gke-test", "managed"], False, "gke-test", "gitops-config/bootstrap/nonprod-managed"),
                ([], True, "eks-test", "gitops-config/bootstrap/nonprod"),
            ):
                with self.subTest(context=context):
                    log.write_text("", encoding="utf-8")
                    command = ('export PATH="$1:$PATH"; shift; bash "$@"')
                    result = subprocess.run(
                        [bash, "-c", command, "bootstrap-test", mock_path,
                         (scripts / source.name).as_posix(), "nonprod", gitops.as_posix(), *args],
                        env=environment, text=True, capture_output=True, timeout=30, check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    calls = log.read_text("utf-8")
                    self.assertEqual("discovery" in calls, discovery)
                    self.assertIn(f"--kube-context {context}", calls)
                    self.assertIn(f"--context {context} --namespace argocd apply", calls)
                    self.assertIn(f'"path":"{root_path}"', calls)


if __name__ == "__main__":
    unittest.main()
