import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


def _posix_path(path: Path) -> str:
    raw = path.as_posix()
    return f"/{raw[0].lower()}{raw[2:]}" if os.name == "nt" and raw[1:2] == ":" else raw


class BootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        win_bash = Path("C:/Program Files/Git/bin/bash.exe")
        self.bash = str(win_bash) if os.name == "nt" and win_bash.exists() else shutil.which("bash")
        self.assertTrue(self.bash and Path(self.bash).exists(), "Bash is required")
        probe = subprocess.run([self.bash, "-c", "true"], capture_output=True, text=True, timeout=10)
        if probe.returncode != 0:
            self.skipTest(f"Bash runtime unavailable in sandbox: {probe.stderr.strip()}")
        self.infra_dir = Path(__file__).resolve().parents[1]

    def _exe(self, path: Path, body: str) -> None:
        path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8", newline="\n")
        path.chmod(0o755)

    def test_bootstrap_supports_all_profiles_and_rejects_invalid_inputs(self) -> None:
        assert self.bash is not None
        src = self.infra_dir / "scripts/bootstrap-argocd.sh"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            shutil.copyfile(src, root / "scripts" / src.name)
            self._exe(root / "scripts/get-kubeconfig.sh", 'echo "disc:$1" >> "$CALL_LOG"\necho "ctx-$1"\n')
            gitops = root / "gitops"
            for rel in ("bootstrap/root-app.yaml", "bootstrap/projects/bootstrap.yaml", "platform/argocd/values.yaml"):
                p = gitops / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("test: fixture\n", encoding="utf-8")
            for tool in ("helm", "kubectl"):
                self._exe(
                    root / tool,
                    f'printf "{tool}|%s\\n" "$*" >> "$CALL_LOG"\nif [[ "$*" == *"-f -" ]]; then cat >/dev/null; fi\n',
                )
            log = root / "calls.log"
            env = dict(os.environ, CALL_LOG=log.as_posix())
            script_p, gitops_p, mock_p = (root / "scripts" / src.name).as_posix(), gitops.as_posix(), _posix_path(root)
            for name, extra, disc, ctx, rpath in (
                ("nonprod", ["eks-1"], False, "eks-1", "gitops-config/bootstrap/nonprod"),
                ("nonprod", ["gke-1", "managed"], False, "gke-1", "gitops-config/bootstrap/nonprod-managed"),
                ("nonprod", [], True, "ctx-nonprod", "gitops-config/bootstrap/nonprod"),
                ("prod", [], True, "ctx-prod", "gitops-config/bootstrap/prod"),
                ("aks", [], True, "ctx-aks", "gitops-config/bootstrap/nonprod-managed"),
                ("gke", [], True, "ctx-gke", "gitops-config/bootstrap/nonprod-managed"),
            ):
                with self.subTest(env=name, extra=extra):
                    log.write_text("", encoding="utf-8")
                    res = subprocess.run(
                        [self.bash, "-c", 'export PATH="$1:$PATH"; shift; bash "$@"', "t", mock_p, script_p, name, gitops_p, *extra],
                        env=env, text=True, capture_output=True, timeout=30,
                    )
                    self.assertEqual(res.returncode, 0, res.stderr)
                    calls = log.read_text("utf-8")
                    self.assertEqual(f"disc:{name}" in calls, disc)
                    self.assertIn(f"--kube-context {ctx}", calls)
                    self.assertIn(f'"path":"{rpath}"', calls)

            for bad in (["prod", gitops_p, "ctx", "managed"], ["staging", gitops_p], ["nonprod", (root / "nope").as_posix()]):
                res = subprocess.run([self.bash, script_p, *bad], env=env, text=True, capture_output=True, timeout=30)
                self.assertEqual(res.returncode, 2)

    def test_get_kubeconfig_supports_eks_aks_gke_and_rejects_unknown_env(self) -> None:
        assert self.bash is not None
        src = self.infra_dir / "scripts/get-kubeconfig.sh"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            for name in ("nonprod", "prod", "aks", "gke"):
                (root / "envs" / name).mkdir(parents=True)
            shutil.copyfile(src, root / "scripts" / src.name)
            self._exe(
                root / "terraform",
                'case "${*: -1}" in cluster_name) echo c1;; cluster_arn) echo arn:eks/c1;; aws_region) echo ap-southeast-1;;'
                ' resource_group_name) echo rg1;; kube_context) echo cloud-ctx;;'
                ' get_credentials_command) echo "gcloud container clusters get-credentials c1 --zone z1 --project p1 --internal-ip";; esac\n',
            )
            for cli in ("aws", "az", "gcloud"):
                self._exe(root / cli, f'printf "{cli}|%s\\n" "$*" >> "$CALL_LOG"\n')
            log = root / "kube.log"
            env = dict(os.environ, CALL_LOG=log.as_posix(), EKS_OPERATOR_PROFILE="ops")
            script_p, mock_p = (root / "scripts" / src.name).as_posix(), _posix_path(root)
            for name, out, cli_prefix in (
                ("nonprod", "arn:eks/c1", "aws|--profile ops eks update-kubeconfig"),
                ("prod", "arn:eks/c1", "aws|--profile ops eks update-kubeconfig"),
                ("aks", "cloud-ctx", "az|aks get-credentials --resource-group rg1 --name c1"),
                ("gke", "cloud-ctx", "gcloud|container clusters get-credentials c1 --zone z1 --project p1 --internal-ip"),
            ):
                log.write_text("", encoding="utf-8")
                res = subprocess.run(
                    [self.bash, "-c", 'export PATH="$1:$PATH"; shift; bash "$@"', "t", mock_p, script_p, name],
                    env=env, text=True, capture_output=True, timeout=30,
                )
                self.assertEqual((res.returncode, res.stdout.strip()), (0, out), res.stderr)
                self.assertIn(cli_prefix, log.read_text("utf-8"))
            self.assertEqual(subprocess.run([self.bash, script_p, "bad"], env=env, capture_output=True, timeout=30).returncode, 2)
