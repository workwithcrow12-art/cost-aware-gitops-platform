#!/usr/bin/env python3
"""Generate real offline Terraform JSON plans across AWS, GCP, and Azure roots without cloud credentials."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SUPPORTED_ENVS: tuple[str, ...] = ("nonprod", "prod", "gke", "aks")

STS_CALLER_IDENTITY_XML = (
    '<GetCallerIdentityResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">'
    "<GetCallerIdentityResult>"
    "<Arn>arn:aws:iam::123456789012:root</Arn>"
    "<UserId>AIDACKCEVSQ6C2EXAMPLE</UserId>"
    "<Account>123456789012</Account>"
    "</GetCallerIdentityResult>"
    "<ResponseMetadata><RequestId>00000000-0000-0000-0000-000000000000</RequestId></ResponseMetadata>"
    "</GetCallerIdentityResponse>"
)

EC2_AVAILABILITY_ZONES_XML = (
    '<DescribeAvailabilityZonesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">'
    "<requestId>00000000-0000-0000-0000-000000000000</requestId>"
    "<availabilityZoneInfo>"
    "<item>"
    "<zoneName>ap-southeast-1a</zoneName>"
    "<zoneId>apse1-az1</zoneId>"
    "<zoneState>available</zoneState>"
    "<regionName>ap-southeast-1</regionName>"
    "<optInStatus>opt-in-not-required</optInStatus>"
    "<zoneType>availability-zone</zoneType>"
    "</item>"
    "<item>"
    "<zoneName>ap-southeast-1b</zoneName>"
    "<zoneId>apse1-az2</zoneId>"
    "<zoneState>available</zoneState>"
    "<regionName>ap-southeast-1</regionName>"
    "<optInStatus>opt-in-not-required</optInStatus>"
    "<zoneType>availability-zone</zoneType>"
    "</item>"
    "<item>"
    "<zoneName>ap-southeast-1c</zoneName>"
    "<zoneId>apse1-az3</zoneId>"
    "<zoneState>available</zoneState>"
    "<regionName>ap-southeast-1</regionName>"
    "<optInStatus>opt-in-not-required</optInStatus>"
    "<zoneType>availability-zone</zoneType>"
    "</item>"
    "</availabilityZoneInfo>"
    "</DescribeAvailabilityZonesResponse>"
)

EC2_ACCOUNT_ATTRIBUTES_XML = (
    '<DescribeAccountAttributesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">'
    "<requestId>00000000-0000-0000-0000-000000000000</requestId>"
    "<accountAttributeSet>"
    "<item>"
    "<attributeName>supported-platforms</attributeName>"
    "<attributeValueSet><item><attributeValue>VPC</attributeValue></item></attributeValueSet>"
    "</item>"
    "</accountAttributeSet>"
    "</DescribeAccountAttributesResponse>"
)

DEFAULT_EKS_ADDON_VERSIONS: dict[str, str] = {
    "vpc-cni": "v1.21.0-eksbuild.1",
    "aws-ebs-csi-driver": "v1.41.0-eksbuild.1",
}


def _b64url_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode("ascii")


def build_mock_azure_jwt(tenant_id: str = "22222222-2222-2222-2222-222222222222") -> str:
    header = _b64url_json({"alg": "none", "typ": "JWT"})
    claims = _b64url_json(
        {
            "appid": "00000000-0000-0000-0000-000000000001",
            "aud": "https://management.azure.com/",
            "exp": 4102444800,
            "iss": f"https://sts.windows.net/{tenant_id}/",
            "oid": "00000000-0000-0000-0000-000000000001",
            "sub": "00000000-0000-0000-0000-000000000001",
            "tid": tenant_id,
        }
    )
    return f"{header}.{claims}.c2ln"


class OfflineCloudStubHandler(BaseHTTPRequestHandler):
    """Stubs read-only AWS STS/EC2/EKS discovery calls and Azure local MSI token requests."""

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send(self, status: int, content_type: str, body: str) -> None:
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _handle_msi_token(self) -> None:
        payload = {
            "access_token": build_mock_azure_jwt(),
            "expires_in": "86400",
            "expires_on": "4102444800",
            "resource": "https://management.azure.com/",
            "token_type": "Bearer",
        }
        self._send(200, "application/json", json.dumps(payload))

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path in ("/msi/token", "/metadata/identity/oauth2/token"):
            self._handle_msi_token()
            return

        if parsed.path == "/addons/supported-versions":
            k8s_version = query.get("kubernetesVersion", ["1.35"])[0]
            requested_addon = query.get("addonName", [None])[0]
            if requested_addon:
                version = DEFAULT_EKS_ADDON_VERSIONS.get(requested_addon, "v1.0.0-eksbuild.1")
                names = [(requested_addon, version)]
            else:
                names = list(DEFAULT_EKS_ADDON_VERSIONS.items())

            addons = [
                {
                    "addonName": name,
                    "addonVersions": [
                        {
                            "addonVersion": ver,
                            "compatibilities": [{"clusterVersion": k8s_version, "defaultVersion": True}],
                        }
                    ],
                }
                for name, ver in names
            ]
            self._send(200, "application/json", json.dumps({"addons": addons}))
            return

        self._send(404, "application/json", json.dumps({"error": f"Unhandled GET path: {parsed.path}"}))

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body_text = self.rfile.read(length).decode("utf-8", errors="replace") if length > 0 else ""

        if parsed.path in ("/msi/token", "/metadata/identity/oauth2/token") or parsed.path.endswith("/oauth2/v2.0/token"):
            self._handle_msi_token()
            return

        params = urllib.parse.parse_qs(body_text)
        if not params and parsed.query:
            params = urllib.parse.parse_qs(parsed.query)
        action = params.get("Action", [""])[0]

        if action == "GetCallerIdentity":
            self._send(200, "text/xml", STS_CALLER_IDENTITY_XML)
            return
        if action == "DescribeAvailabilityZones":
            self._send(200, "text/xml", EC2_AVAILABILITY_ZONES_XML)
            return
        if action == "DescribeAccountAttributes":
            self._send(200, "text/xml", EC2_ACCOUNT_ATTRIBUTES_XML)
            return

        self._send(200, "text/xml", "<Response/>")


class OfflineCloudStubServer:
    """Context manager running OfflineCloudStubHandler on 127.0.0.1:<ephemeral_port>."""

    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), OfflineCloudStubHandler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, name="offline-cloud-stub", daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> OfflineCloudStubServer:
        self._thread.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


_BACKEND_START_RE = re.compile(r'\bbackend\s+"[^"]+"\s*\{')


def strip_terraform_backends(hcl_text: str) -> str:
    """Remove any `backend "<name>" { ... }` block while keeping surrounding HCL intact."""
    result: list[str] = []
    cursor = 0
    while True:
        match = _BACKEND_START_RE.search(hcl_text, cursor)
        if match is None:
            result.append(hcl_text[cursor:])
            break
        result.append(hcl_text[cursor : match.start()])
        depth = 1
        idx = match.end()
        in_string = False
        escape = False
        while idx < len(hcl_text) and depth > 0:
            ch = hcl_text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
            idx += 1
        while idx < len(hcl_text) and hcl_text[idx] in (" ", "\t"):
            idx += 1
        if idx < len(hcl_text) and hcl_text[idx] == "\n":
            idx += 1
        cursor = idx
    return "".join(result)


def build_override_hcl(env_name: str, stub_base_url: str) -> str:
    if env_name in ("nonprod", "prod"):
        return (
            'provider "aws" {\n'
            '  access_key                  = "mock"\n'
            '  secret_key                  = "mock"\n'
            "  skip_credentials_validation = true\n"
            "  skip_metadata_api_check     = true\n"
            "  skip_requesting_account_id  = true\n\n"
            "  endpoints {\n"
            f'    ec2 = "{stub_base_url}"\n'
            f'    eks = "{stub_base_url}"\n'
            f'    sts = "{stub_base_url}"\n'
            "  }\n"
            "}\n"
        )
    if env_name == "gke":
        return (
            'provider "google" {\n'
            '  access_token = "ya29.offline-ci-mock-token"\n'
            "}\n"
        )
    if env_name == "aks":
        return (
            'provider "azurerm" {\n'
            "  features {}\n"
            '  resource_provider_registrations = "none"\n'
            "  use_cli                         = false\n"
            "  use_msi                         = true\n"
            f'  msi_endpoint                    = "{stub_base_url}/msi/token"\n'
            "}\n"
        )
    raise ValueError(f"Unsupported environment: {env_name}")


def build_offline_tfvars(env_name: str) -> dict[str, Any]:
    if env_name in ("nonprod", "prod"):
        monthly_limit = 500 if env_name == "prod" else 150
        return {
            "operator_role_arn": "arn:aws:iam::123456789012:role/ClusterOperator",
            "operator_access_policy": "AmazonEKSViewPolicy",
            "break_glass_role_arn": "arn:aws:iam::123456789012:role/ClusterBreakGlass",
            "operator_access_cidrs": ["10.50.0.0/24"],
            "enable_interface_endpoints": True,
            "enable_karpenter": True,
            "budget": {
                "monthly_limit_usd": monthly_limit,
                "email": "finops@example.com",
            },
            "cost_reporting": {
                "enable_reporter": True,
                "cur_catalog": {
                    "database_name": f"finops_{env_name}",
                    "table_name": "cur",
                    "data_s3": "s3://cost-aware-cur-mock/cur/parquet/",
                },
            },
            "github_oidc": {
                "roles": {
                    "apply": {
                        "subjects": [f"repo:example/platform:environment:{env_name}"],
                        "policy_arn": "arn:aws:iam::123456789012:policy/TerraformApply",
                    }
                }
            },
        }
    if env_name == "gke":
        return {
            "project_id": "cost-aware-offline-ci",
            "operator_member": "group:platform@example.com",
            "operator_access_cidrs": ["10.50.0.0/24"],
        }
    if env_name == "aks":
        return {
            "subscription_id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": "22222222-2222-2222-2222-222222222222",
            "operator_group_object_id": "33333333-3333-3333-3333-333333333333",
        }
    raise ValueError(f"Unsupported environment: {env_name}")


def _link_or_copy_providers(src_env: Path, dst_env: Path) -> None:
    src_providers = src_env / ".terraform" / "providers"
    if not src_providers.is_dir():
        return
    dst_tf_dir = dst_env / ".terraform"
    dst_tf_dir.mkdir(parents=True, exist_ok=True)
    dst_providers = dst_tf_dir / "providers"
    try:
        os.symlink(src_providers.resolve(), dst_providers, target_is_directory=True)
    except OSError:
        shutil.copytree(src_providers, dst_providers)


def stage_infra_tree(
    infra_dir: Path,
    stage_root: Path,
    envs: tuple[str, ...] | list[str],
    stub_base_url: str,
) -> dict[str, Path]:
    """Copy modules and target envs into stage_root, stripping remote backends and writing offline overrides."""
    src_modules = infra_dir / "modules"
    if not src_modules.is_dir():
        raise FileNotFoundError(f"Modules directory not found: {src_modules}")

    shutil.copytree(
        src_modules,
        stage_root / "modules",
        ignore=shutil.ignore_patterns(".terraform", "*.tfstate*", "*.tftest.hcl", "tfplan"),
    )

    staged_envs: dict[str, Path] = {}
    for env_name in envs:
        src_env = infra_dir / "envs" / env_name
        if not src_env.is_dir():
            raise FileNotFoundError(f"Environment directory not found: {src_env}")
        dst_env = stage_root / "envs" / env_name
        dst_env.mkdir(parents=True, exist_ok=True)

        for item in sorted(src_env.iterdir()):
            if item.name in (".terraform", "backend.tf", "tfplan"):
                continue
            if item.name.endswith((".tftest.hcl", ".tfstate", ".tfstate.backup")) or item.is_dir():
                continue
            if item.suffix == ".tf":
                cleaned = strip_terraform_backends(item.read_text(encoding="utf-8"))
                (dst_env / item.name).write_text(cleaned, encoding="utf-8", newline="\n")
            else:
                shutil.copy2(item, dst_env / item.name)

        _link_or_copy_providers(src_env, dst_env)
        (dst_env / "_ci_offline_override.tf").write_text(
            build_override_hcl(env_name, stub_base_url),
            encoding="utf-8",
            newline="\n",
        )
        (dst_env / "_ci_offline.tfvars.json").write_text(
            json.dumps(build_offline_tfvars(env_name), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        staged_envs[env_name] = dst_env

    return staged_envs


def _sanitized_terraform_env() -> dict[str, str]:
    blocked_prefixes = (
        "AWS_",
        "GOOGLE_",
        "GCLOUD_",
        "CLOUDSDK_",
        "ARM_",
        "AZURE_",
        "MSI_",
        "IDENTITY_",
        "TF_VAR_",
    )
    clean = {k: v for k, v in os.environ.items() if not k.startswith(blocked_prefixes)}
    clean.update(
        {
            "AWS_ACCESS_KEY_ID": "mock",
            "AWS_SECRET_ACCESS_KEY": "mock",
            "AWS_EC2_METADATA_DISABLED": "true",
            "ARM_PROVIDER_ENHANCED_VALIDATION": "false",
            "ARM_USE_CLI": "false",
            "CHECKPOINT_DISABLE": "1",
            "TF_IN_AUTOMATION": "1",
        }
    )
    return clean


def _run_tf(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, env=env, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        cmd_str = " ".join(args)
        details = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"Command failed ({proc.returncode}): {cmd_str}\n{details}")
    return proc


def generate_offline_plans(
    infra_dir: Path,
    output_dir: Path,
    envs: tuple[str, ...] | list[str] = SUPPORTED_ENVS,
    terraform_bin: str = "terraform",
) -> dict[str, Path]:
    """Run offline init/plan/show across target roots and write JSON plans to output_dir."""
    infra_dir = infra_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    tf_env = _sanitized_terraform_env()
    written: dict[str, Path] = {}

    with OfflineCloudStubServer() as stub, tempfile.TemporaryDirectory(prefix="tf-offline-plan-") as tmp:
        staged_envs = stage_infra_tree(infra_dir, Path(tmp), envs, stub.base_url)
        for env_name in envs:
            staged_env = staged_envs[env_name]
            chdir = f"-chdir={staged_env}"
            _run_tf([terraform_bin, chdir, "init", "-backend=false", "-input=false"], tf_env)
            _run_tf(
                [
                    terraform_bin,
                    chdir,
                    "plan",
                    "-refresh=false",
                    "-input=false",
                    "-var-file=_ci_offline.tfvars.json",
                    "-out=tfplan",
                ],
                tf_env,
            )
            show_proc = _run_tf([terraform_bin, chdir, "show", "-json", "tfplan"], tf_env)
            plan_json = json.loads(show_proc.stdout)
            changes = plan_json.get("resource_changes")
            if not isinstance(changes, list) or len(changes) == 0:
                raise RuntimeError(f"Offline plan for '{env_name}' produced zero resource_changes.")

            out_file = output_dir / f"{env_name}.json"
            out_file.write_text(json.dumps(plan_json, indent=2) + "\n", encoding="utf-8", newline="\n")
            written[env_name] = out_file

    return written


def build_arg_parser() -> argparse.ArgumentParser:
    default_infra_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Generate real offline Terraform JSON plans for Conftest policy verification."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where <env>.json plan files will be written.",
    )
    parser.add_argument(
        "--infra-dir",
        type=Path,
        default=default_infra_dir,
        help="Path to the platform-infra directory (defaults to parent of scripts/).",
    )
    parser.add_argument(
        "--envs",
        nargs="+",
        choices=SUPPORTED_ENVS,
        default=list(SUPPORTED_ENVS),
        help="Subset of environments to plan (defaults to nonprod prod gke aks).",
    )
    parser.add_argument(
        "--terraform-bin",
        default=os.environ.get("TERRAFORM_BIN", "terraform"),
        help="Terraform CLI binary name or path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    written = generate_offline_plans(
        infra_dir=args.infra_dir,
        output_dir=args.output_dir,
        envs=args.envs,
        terraform_bin=args.terraform_bin,
    )
    for env_name, path in written.items():
        print(f"[offline-plan] {env_name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
