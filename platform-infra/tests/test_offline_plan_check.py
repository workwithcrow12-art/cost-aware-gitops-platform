from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import offline_plan_check  # noqa: E402


def _http_request(url: str, method: str = "GET", data: dict[str, str] | None = None) -> tuple[int, str]:
    encoded = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=encoded, method=method)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, resp.read().decode("utf-8")


class OfflineStubServerTests(unittest.TestCase):
    def test_aws_sts_ec2_eks_and_azure_msi_endpoints(self) -> None:
        with offline_plan_check.OfflineCloudStubServer() as stub:
            status, sts_xml = _http_request(stub.base_url, method="POST", data={"Action": "GetCallerIdentity"})
            self.assertEqual(status, 200)
            self.assertIn("<Account>123456789012</Account>", sts_xml)
            self.assertIn("<Arn>arn:aws:iam::123456789012:root</Arn>", sts_xml)

            status, az_xml = _http_request(stub.base_url, method="POST", data={"Action": "DescribeAvailabilityZones"})
            self.assertEqual(status, 200)
            for zone in ("ap-southeast-1a", "ap-southeast-1b", "ap-southeast-1c"):
                self.assertIn(f"<zoneName>{zone}</zoneName>", az_xml)
            self.assertIn("<optInStatus>opt-in-not-required</optInStatus>", az_xml)

            status, attr_xml = _http_request(stub.base_url, method="POST", data={"Action": "DescribeAccountAttributes"})
            self.assertEqual(status, 200)
            self.assertIn("supported-platforms", attr_xml)

            status, fallback_xml = _http_request(stub.base_url, method="POST", data={"Action": "UnknownReadOnlyCall"})
            self.assertEqual(status, 200)
            self.assertEqual(fallback_xml, "<Response/>")

            status, all_addons_raw = _http_request(f"{stub.base_url}/addons/supported-versions")
            self.assertEqual(status, 200)
            all_addons = json.loads(all_addons_raw)["addons"]
            self.assertEqual({a["addonName"] for a in all_addons}, {"vpc-cni", "aws-ebs-csi-driver"})

            status, single_addon_raw = _http_request(
                f"{stub.base_url}/addons/supported-versions?addonName=vpc-cni&kubernetesVersion=1.35"
            )
            self.assertEqual(status, 200)
            single_addons = json.loads(single_addon_raw)["addons"]
            self.assertEqual(len(single_addons), 1)
            self.assertEqual(single_addons[0]["addonName"], "vpc-cni")
            self.assertEqual(single_addons[0]["addonVersions"][0]["addonVersion"], "v1.21.0-eksbuild.1")

            for method in ("GET", "POST"):
                status, msi_raw = _http_request(f"{stub.base_url}/msi/token", method=method, data={} if method == "POST" else None)
                self.assertEqual(status, 200)
                msi = json.loads(msi_raw)
                self.assertEqual(msi["token_type"], "Bearer")
                self.assertEqual(msi["expires_on"], "4102444800")
                segments = msi["access_token"].split(".")
                self.assertEqual(len(segments), 3)
                padded = segments[1] + "=" * (-len(segments[1]) % 4)
                claims = json.loads(base64.urlsafe_b64decode(padded))
                self.assertEqual(claims["tid"], "22222222-2222-2222-2222-222222222222")
                self.assertEqual(claims["exp"], 4102444800)


class OfflinePlanStagingAndExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.infra_dir = Path(__file__).resolve().parents[1]

    def test_strip_terraform_backends_handles_nested_blocks(self) -> None:
        source = (
            "terraform {\n"
            '  required_version = "~> 1.11.0"\n'
            '  backend "s3" {\n'
            '    key     = "prod/terraform.tfstate"\n'
            "    encrypt = true\n"
            "  }\n"
            "}\n"
        )
        cleaned = offline_plan_check.strip_terraform_backends(source)
        self.assertNotIn('backend "s3"', cleaned)
        self.assertIn('required_version = "~> 1.11.0"', cleaned)

    def test_stage_infra_tree_creates_overrides_tfvars_and_strips_backends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage_root = Path(tmp)
            staged = offline_plan_check.stage_infra_tree(
                self.infra_dir,
                stage_root,
                offline_plan_check.SUPPORTED_ENVS,
                "http://127.0.0.1:43210",
            )
            self.assertEqual(set(staged.keys()), set(offline_plan_check.SUPPORTED_ENVS))
            self.assertTrue((stage_root / "modules" / "cluster" / "main.tf").is_file())

            for env_name in ("nonprod", "prod"):
                env_dir = staged[env_name]
                self.assertFalse((env_dir / "backend.tf").exists())
                override = (env_dir / "_ci_offline_override.tf").read_text(encoding="utf-8")
                self.assertIn('skip_credentials_validation = true', override)
                self.assertIn('sts = "http://127.0.0.1:43210"', override)
                tfvars = json.loads((env_dir / "_ci_offline.tfvars.json").read_text(encoding="utf-8"))
                self.assertTrue(tfvars["enable_karpenter"])
                self.assertTrue(tfvars["enable_interface_endpoints"])
                self.assertEqual(tfvars["operator_access_policy"], "AmazonEKSViewPolicy")
                self.assertNotEqual(tfvars["break_glass_role_arn"], tfvars["operator_role_arn"])
                self.assertGreater(tfvars["budget"]["monthly_limit_usd"], 0)
                self.assertTrue(tfvars["cost_reporting"]["enable_reporter"])
                self.assertIn("apply", tfvars["github_oidc"]["roles"])

            gke_override = (staged["gke"] / "_ci_offline_override.tf").read_text(encoding="utf-8")
            self.assertIn('access_token = "ya29.offline-ci-mock-token"', gke_override)

            aks_override = (staged["aks"] / "_ci_offline_override.tf").read_text(encoding="utf-8")
            self.assertIn('resource_provider_registrations = "none"', aks_override)
            self.assertIn("use_cli                         = false", aks_override)
            self.assertIn("use_msi                         = true", aks_override)
            self.assertIn('msi_endpoint                    = "http://127.0.0.1:43210/msi/token"', aks_override)
            self.assertNotIn("skip_provider_registration", aks_override)

    def test_aks_override_and_sanitized_env_disable_live_arm_discovery(self) -> None:
        aks_override = offline_plan_check.build_override_hcl("aks", "http://127.0.0.1:43210")
        self.assertIn('resource_provider_registrations = "none"', aks_override)
        self.assertIn("use_cli                         = false", aks_override)
        self.assertIn("use_msi                         = true", aks_override)
        self.assertIn('msi_endpoint                    = "http://127.0.0.1:43210/msi/token"', aks_override)
        self.assertNotIn("skip_provider_registration", aks_override)

        ambient = {
            "PATH": "/usr/bin",
            "ARM_SKIP_PROVIDER_REGISTRATION": "true",
            "ARM_CLIENT_SECRET": "super-secret",
            "AZURE_CONFIG_DIR": "/tmp/azure",
        }
        with mock.patch.dict("offline_plan_check.os.environ", ambient, clear=True):
            env = offline_plan_check._sanitized_terraform_env()

        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertNotIn("ARM_SKIP_PROVIDER_REGISTRATION", env)
        self.assertNotIn("ARM_CLIENT_SECRET", env)
        self.assertNotIn("AZURE_CONFIG_DIR", env)
        self.assertEqual(env["ARM_PROVIDER_ENHANCED_VALIDATION"], "false")
        self.assertEqual(env["ARM_USE_CLI"], "false")

    def test_reuses_initialized_provider_directory_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as fake_infra_str, tempfile.TemporaryDirectory() as stage_str:
            fake_infra = Path(fake_infra_str)
            (fake_infra / "modules" / "dummy").mkdir(parents=True)
            (fake_infra / "modules" / "dummy" / "main.tf").write_text("", encoding="utf-8")
            env_dir = fake_infra / "envs" / "gke"
            provider_marker = env_dir / ".terraform" / "providers" / "registry.terraform.io" / "marker.txt"
            provider_marker.parent.mkdir(parents=True)
            provider_marker.write_text("cached-provider", encoding="utf-8")
            (env_dir / "main.tf").write_text('provider "google" {}\n', encoding="utf-8")

            staged = offline_plan_check.stage_infra_tree(fake_infra, Path(stage_str), ("gke",), "http://127.0.0.1:9999")
            staged_marker = staged["gke"] / ".terraform" / "providers" / "registry.terraform.io" / "marker.txt"
            self.assertTrue(staged_marker.is_file())
            self.assertEqual(staged_marker.read_text(encoding="utf-8"), "cached-provider")

    def test_cli_main_runs_init_plan_show_and_validates_resource_changes(self) -> None:
        calls: list[list[str]] = []

        def fake_run(args: list[str], env: dict[str, str], text: bool, capture_output: bool, check: bool) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            self.assertEqual(env["AWS_ACCESS_KEY_ID"], "mock")
            self.assertEqual(env["AWS_EC2_METADATA_DISABLED"], "true")
            self.assertEqual(env["ARM_PROVIDER_ENHANCED_VALIDATION"], "false")
            self.assertEqual(env["ARM_USE_CLI"], "false")
            self.assertNotIn("ARM_SKIP_PROVIDER_REGISTRATION", env)
            if "show" in args:
                payload = {
                    "format_version": "1.2",
                    "resource_changes": [
                        {
                            "address": "example_resource.this",
                            "mode": "managed",
                            "type": "aws_vpc",
                            "change": {"actions": ["create"], "after": {"tags_all": {"env": "prod"}}},
                        }
                    ],
                }
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")
            return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

        with tempfile.TemporaryDirectory() as out_tmp, mock.patch("offline_plan_check.subprocess.run", side_effect=fake_run):
            out_dir = Path(out_tmp) / "plans"
            rc = offline_plan_check.main(["--output-dir", str(out_dir), "--infra-dir", str(self.infra_dir)])
            self.assertEqual(rc, 0)
            for env_name in offline_plan_check.SUPPORTED_ENVS:
                plan_path = out_dir / f"{env_name}.json"
                self.assertTrue(plan_path.is_file())
                parsed = json.loads(plan_path.read_text(encoding="utf-8"))
                self.assertEqual(len(parsed["resource_changes"]), 1)

        self.assertEqual(len(calls), 4 * 3)

    def test_rejects_empty_resource_changes_and_failed_terraform_command(self) -> None:
        def empty_show_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            out = json.dumps({"resource_changes": []}) if "show" in args else "ok"
            return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

        with tempfile.TemporaryDirectory() as out_tmp, mock.patch("offline_plan_check.subprocess.run", side_effect=empty_show_run):
            with self.assertRaisesRegex(RuntimeError, "zero resource_changes"):
                offline_plan_check.generate_offline_plans(self.infra_dir, Path(out_tmp), envs=("gke",))

        def failing_plan_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if "plan" in args:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="missing variable")
            return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

        with tempfile.TemporaryDirectory() as out_tmp, mock.patch("offline_plan_check.subprocess.run", side_effect=failing_plan_run):
            with self.assertRaisesRegex(RuntimeError, "missing variable"):
                offline_plan_check.generate_offline_plans(self.infra_dir, Path(out_tmp), envs=("prod",))


class TerraformGovernanceFormattingTests(unittest.TestCase):
    """Static checks ensuring HCL formatting (`terraform fmt` style) and governance contracts hold."""

    def setUp(self) -> None:
        self.infra_dir = Path(__file__).resolve().parents[1]

    def test_hcl_files_have_two_space_indent_balanced_delimiters_and_aligned_equals(self) -> None:
        single_attr_re = re.compile(r'^(?P<indent> *)(?P<key>[A-Za-z0-9_."-]+)(?P<spaces> +)= (?P<rhs>.+)$')
        hcl_files = sorted(
            p
            for p in self.infra_dir.rglob("*")
            if p.is_file() and (p.name.endswith(".tf") or p.name.endswith(".tftest.hcl"))
        )
        self.assertGreater(len(hcl_files), 20)

        for path in hcl_files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("\t", text, f"Tab character found in {path}")
            lines = text.splitlines()

            group: list[tuple[int, str, int]] = []
            open_multiline = 0

            def flush_group(file_path: Path = path) -> None:
                if len(group) > 1:
                    max_key = max(len(k) for _, k, _ in group)
                    for lineno, key, spaces in group:
                        expected = max_key - len(key) + 1
                        self.assertEqual(
                            spaces,
                            expected,
                            f"{file_path}:{lineno} misaligned '=' for '{key}' (got {spaces} spaces, expected {expected})",
                        )
                group.clear()

            for lineno, line in enumerate(lines, start=1):
                self.assertEqual(line.rstrip(" "), line, f"Trailing spaces at {path}:{lineno}")
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                    if open_multiline == 0:
                        flush_group()
                    continue

                leading = len(line) - len(line.lstrip(" "))
                self.assertEqual(leading % 2, 0, f"Odd indentation ({leading}) at {path}:{lineno}")

                unquoted = re.sub(r'"(?:\\.|[^"\\])*"', '""', stripped)
                delta = (
                    unquoted.count("{")
                    - unquoted.count("}")
                    + unquoted.count("[")
                    - unquoted.count("]")
                    + unquoted.count("(")
                    - unquoted.count(")")
                )

                if open_multiline > 0:
                    open_multiline += delta
                    continue

                match = single_attr_re.match(line)
                if match and delta == 0 and not unquoted.endswith("{"):
                    group.append((lineno, match.group("key"), len(match.group("spaces"))))
                else:
                    flush_group()
                    if delta > 0 and "=" in unquoted and not unquoted.lstrip().startswith(("for ", "dynamic ")):
                        # Multi-line attribute assignment must use a single space before '='.
                        lhs_eq = re.match(r"^ *[A-Za-z0-9_.\"-]+( +)= ", line)
                        if lhs_eq:
                            self.assertEqual(
                                len(lhs_eq.group(1)),
                                1,
                                f"{path}:{lineno} multi-line attribute should have 1 space before '='",
                            )
                        open_multiline += delta

            flush_group()

    def test_prod_budget_nat_and_operator_governance_contracts(self) -> None:
        prod_vars = (self.infra_dir / "envs" / "prod" / "variables.tf").read_text(encoding="utf-8")
        self.assertIn('"Required environment-filtered monthly AWS Budget for production."', prod_vars)
        self.assertIn('variable "nat_per_az"', prod_vars)
        self.assertIn('variable "operator_access_policy"', prod_vars)
        self.assertIn('variable "break_glass_role_arn"', prod_vars)

        prod_outputs = (self.infra_dir / "envs" / "prod" / "outputs.tf").read_text(encoding="utf-8")
        self.assertIn("value = module.budget.budget_name", prod_outputs)
        self.assertNotIn("module.budget[0]", prod_outputs)

        infracost_cfg = (self.infra_dir / "infracost.yml").read_text(encoding="utf-8")
        for project_name in ("aws-nonprod", "aws-prod", "gcp-gke", "azure-aks"):
            self.assertIn(f"name: {project_name}", infracost_cfg)
        self.assertIn("monthly_limit_usd: 500", infracost_cfg)


if __name__ == "__main__":
    unittest.main()
