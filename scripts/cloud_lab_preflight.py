"""Offline-first cloud lab preflight readiness check and Decimal cost estimator."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
HOURS_PER_30_DAYS = Decimal("720")
CENT = Decimal("0.01")
HOURLY_PRECISION = Decimal("0.0001")

IAM_ROLE_ARN_RE = re.compile(
    r"^arn:aws(-[a-z]+)*:iam::[0-9]{12}:role/[A-Za-z0-9_+=,.@/-]+$"
)
ACCOUNT_ID_RE = re.compile(r"(?<![0-9a-fA-F])[0-9]{12}(?![0-9a-fA-F])")
ARN_RE = re.compile(r"arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:(?:[0-9]{12}|aws)?:[^\s\"'`<>]+")


@dataclass(frozen=True)
class ToolStatus:
    name: str
    required: bool
    found: bool
    note: str


@dataclass(frozen=True)
class EnvVarStatus:
    name: str
    required: bool
    configured: bool
    valid: bool
    detail: str


@dataclass(frozen=True)
class CostItem:
    component: str
    spec: str
    hourly_usd: Decimal
    session_usd: Decimal
    monthly_30d_usd: Decimal


@dataclass(frozen=True)
class IdentityStatus:
    requested: bool
    verified: bool | None
    detail: str


@dataclass(frozen=True)
class PreflightReport:
    env: str
    region: str
    hours: Decimal
    generated_utc: str
    ready: bool
    tools: list[ToolStatus]
    env_vars: list[EnvVarStatus]
    identity: IdentityStatus
    cost_items: list[CostItem]
    total_hourly_usd: Decimal
    total_session_usd: Decimal
    total_monthly_30d_usd: Decimal
    comparison_notes: list[str]
    private_api_warning: str
    free_tier_cautions: list[str]
    blockers: list[str]


def mask_identifiers(text: str) -> str:
    """Mask AWS ARNs and 12-digit account IDs before displaying diagnostics."""
    masked = ARN_RE.sub("<REDACTED_ARN>", text)
    return ACCOUNT_ID_RE.sub("<REDACTED_ACCOUNT_ID>", masked)


def parse_hours(raw: float | str | Decimal) -> Decimal:
    """Convert hours to a positive finite Decimal without binary float drift."""
    if isinstance(raw, bool):
        raise ValueError("hours must be a positive finite number")
    if isinstance(raw, float):
        if not math.isfinite(raw):
            raise ValueError("hours must be a positive finite number")
        value = Decimal(str(raw))
    else:
        try:
            value = Decimal(str(raw).strip())
        except InvalidOperation as exc:
            raise ValueError("hours must be a positive finite number") from exc
    if not value.is_finite() or value <= Decimal("0"):
        raise ValueError("hours must be greater than zero")
    return value


def format_usd(amount: Decimal) -> str:
    quantized = amount.quantize(CENT, rounding=ROUND_HALF_UP)
    formatted = f"{abs(quantized):,.2f}"
    return f"-${formatted}" if quantized < Decimal("0") and formatted != "0.00" else f"${formatted}"


def format_hourly_usd(amount: Decimal) -> str:
    quantized = amount.quantize(HOURLY_PRECISION, rounding=ROUND_HALF_UP)
    return f"${quantized:,.4f}/hr"


def _build_cost_item(component: str, spec: str, hourly: str, hours: Decimal) -> CostItem:
    hourly_dec = Decimal(hourly)
    if not hourly_dec.is_finite() or hourly_dec < Decimal("0"):
        raise ValueError(f"Invalid hourly rate for {component}: {hourly}")
    return CostItem(
        component=component,
        spec=spec,
        hourly_usd=hourly_dec,
        session_usd=(hourly_dec * hours).quantize(CENT, rounding=ROUND_HALF_UP),
        monthly_30d_usd=(hourly_dec * HOURS_PER_30_DAYS).quantize(CENT, rounding=ROUND_HALF_UP),
    )


def estimate_costs(env: str, hours: Decimal) -> tuple[str, list[CostItem], list[str]]:
    """Compute itemized regional hourly, session, and 30-day Decimal estimates."""
    if env == "nonprod":
        region = "ap-southeast-1"
        items = [
            _build_cost_item(
                "EKS control plane",
                "1 cluster (Standard support)",
                "0.1000",
                hours,
            ),
            _build_cost_item(
                "System node group (Spot)",
                "2x m6i.large Spot (~$0.0380/hr each)",
                "0.0760",
                hours,
            ),
            _build_cost_item(
                "Shared NAT Gateway",
                "1x NAT Gateway (nat_per_az = false, excl. $0.059/GB data)",
                "0.0590",
                hours,
            ),
            _build_cost_item(
                "Worker gp3 EBS root volumes",
                "2x 20 GiB gp3 @ ~$0.096/GiB-month",
                "0.0053",
                hours,
            ),
        ]
        on_demand_hourly = Decimal("0.1000") + Decimal("0.2400") + Decimal("0.0590") + Decimal("0.0053")
        on_demand_session = (on_demand_hourly * hours).quantize(CENT, rounding=ROUND_HALF_UP)
        on_demand_30d = (on_demand_hourly * HOURS_PER_30_DAYS).quantize(CENT, rounding=ROUND_HALF_UP)
        notes = [
            (
                "Spot vs On-Demand comparison (`ap-southeast-1`): replacing 2x `m6i.large` Spot "
                f"(`$0.0760/hr`) with On-Demand (`2x $0.1200/hr = $0.2400/hr`) raises the cluster "
                f"baseline to {format_hourly_usd(on_demand_hourly)} ({format_usd(on_demand_session)} "
                f"for {hours}h; {format_usd(on_demand_30d)}/30d)."
            ),
            (
                "1 vs 3 NAT Gateways: `nonprod` uses 1 shared NAT Gateway (`$0.0590/hr`, "
                "`$42.48/30d`) across 2 AZs, trading AZ-isolated egress for lower lab spend."
            ),
            (
                "Off-hours pod downscaling (`GoKubeDownscaler`) reduces replica counts outside "
                "08:00-20:00 ICT on weekdays, but fixed managed node groups still bill for 2 EC2 instances "
                "until cluster teardown or node autoscaling is enabled."
            ),
        ]
        return region, items, notes

    if env == "prod":
        region = "ap-southeast-1"
        items = [
            _build_cost_item(
                "EKS control plane",
                "1 cluster (Standard support)",
                "0.1000",
                hours,
            ),
            _build_cost_item(
                "System node group (On-Demand)",
                "3x m6i.large On-Demand ($0.1200/hr each)",
                "0.3600",
                hours,
            ),
            _build_cost_item(
                "HA NAT Gateways",
                "3x NAT Gateway (nat_per_az = true, excl. $0.059/GB data)",
                "0.1770",
                hours,
            ),
            _build_cost_item(
                "Encrypted gp3 EBS volumes",
                "3x 20 GiB worker root + 20 GiB Prometheus PVC (Retain)",
                "0.0107",
                hours,
            ),
        ]
        single_nat_hourly = Decimal("0.1000") + Decimal("0.3600") + Decimal("0.0590") + Decimal("0.0107")
        single_nat_30d = (single_nat_hourly * HOURS_PER_30_DAYS).quantize(CENT, rounding=ROUND_HALF_UP)
        notes = [
            (
                "1 vs 3 NAT Gateways (`nat_per_az`): `prod` defaults to `nat_per_az = true` "
                "(`3x $0.0590/hr = $0.1770/hr`, `$127.44/30d` or `~$129.21/730h` billing month before "
                "per-GB data processing). Setting `TF_VAR_nat_per_az=false` lowers fixed NAT spend to "
                f"`$0.0590/hr` (bringing total baseline to {format_hourly_usd(single_nat_hourly)}, "
                f"{format_usd(single_nat_30d)}/30d) at the cost of cross-AZ NAT traffic charges and "
                "single-AZ egress failure blast radius."
            ),
            (
                "Production Prometheus requests a 20 GiB `gp3` PVC with `reclaimPolicy: Retain`; "
                "delete retained EBS volumes explicitly after `terraform destroy` to stop storage billing."
            ),
        ]
        return region, items, notes

    if env == "gke":
        region = "asia-southeast1"
        items = [
            _build_cost_item(
                "GKE zonal cluster fee",
                "1 zonal cluster (waived only if eligible for 1 free zonal cluster/billing account)",
                "0.1000",
                hours,
            ),
            _build_cost_item(
                "System node pool (On-Demand)",
                "2x e2-standard-4 ($0.1509/hr each)",
                "0.3018",
                hours,
            ),
            _build_cost_item(
                "Cloud NAT gateway",
                "Regional Cloud Router + NAT minimum hourly charge",
                "0.0450",
                hours,
            ),
            _build_cost_item(
                "Node boot persistent disks",
                "2x 30 GiB pd-balanced",
                "0.0092",
                hours,
            ),
        ]
        notes = [
            (
                "Zonal lab scope: `envs/gke` provisions a single-zone (`asia-southeast1-a`) private "
                "cluster with `deletion_protection = true` by default; apply `deletion_protection = false` "
                "before running `terraform destroy`."
            ),
        ]
        return region, items, notes

    if env == "aks":
        region = "southeastasia"
        items = [
            _build_cost_item(
                "AKS control plane (Free tier)",
                "1 private cluster without uptime SLA (Standard tier adds $0.1000/hr)",
                "0.0000",
                hours,
            ),
            _build_cost_item(
                "System node pool (On-Demand)",
                "2x Standard_D4s_v5 ($0.2280/hr each)",
                "0.4560",
                hours,
            ),
            _build_cost_item(
                "Standard Load Balancer",
                "Outbound NAT rules baseline (excl. data processed)",
                "0.0250",
                hours,
            ),
            _build_cost_item(
                "Managed OS disks",
                "2x 30 GiB managed OS disks",
                "0.0067",
                hours,
            ),
        ]
        notes = [
            (
                "AKS lab scope: `envs/aks` disables local Kubernetes admin accounts and binds "
                "cluster administration to the configured Microsoft Entra group (`kubelogin` required)."
            ),
        ]
        return region, items, notes

    raise ValueError(f"Unsupported environment: {env}")


def _validate_cidrs(raw: str) -> tuple[bool, str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return False, "Invalid JSON list; expected e.g. '[\"10.20.1.0/24\"]'"
    if not isinstance(parsed, list) or not parsed or not all(isinstance(x, str) and x.strip() for x in parsed):
        return False, "Expected a non-empty JSON list of IPv4 CIDR strings"
    for item in parsed:
        cidr = item.strip()
        if cidr.endswith("/0") or "/" not in cidr:
            return False, "Operator CIDRs must be valid private IPv4 ranges and must exclude /0"
    return True, f"Configured ({len(parsed)} private CIDR entry/entries)"


def _validate_budget_var(raw: str) -> tuple[bool, str]:
    stripped = raw.strip()
    if not stripped:
        return False, "Missing required production budget configuration"
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                limit = parsed.get("monthly_limit_usd")
                email = str(parsed.get("email", "")).strip()
                if isinstance(limit, (int, float)) and not isinstance(limit, bool) and limit > 0 and "@" in email:
                    return True, f"Configured JSON budget (monthly_limit_usd={limit})"
                return False, "TF_VAR_budget JSON must include monthly_limit_usd > 0 and a valid email"
        except json.JSONDecodeError:
            pass
    if "monthly_limit_usd" in stripped and "email" in stripped:
        return True, "Configured HCL object budget"
    return False, "Expected HCL/JSON object with monthly_limit_usd > 0 and notification email"


def _check_tools(
    env: str,
    which: Callable[[str], str | None],
) -> list[ToolStatus]:
    common = [
        ("terraform", True, "Infrastructure init/plan/apply (pin 1.11.4 per platform-infra/.tool-versions)"),
        ("kubectl", True, "Cluster verification and Kustomize manifest inspection (pin 1.35.0)"),
        ("helm", True, "Argo CD bootstrap release installation (pin 3.18.6)"),
        ("kubeseal", True, "Cluster-bound SealedSecret encryption for redis-cart and notifications"),
    ]
    cloud_specific = {
        "nonprod": [("aws", True, "AWS STS verification and eks update-kubeconfig")],
        "prod": [("aws", True, "AWS STS verification and eks update-kubeconfig")],
        "gke": [("gcloud", True, "GKE private endpoint kubeconfig and ADC authentication")],
        "aks": [
            ("az", True, "AKS credential retrieval and subscription context"),
            ("kubelogin", True, "Entra ID kubeconfig token conversion for local_account_disabled=true"),
        ],
    }[env]
    results: list[ToolStatus] = []
    for name, required, note in [*common, *cloud_specific]:
        path = which(name)
        results.append(
            ToolStatus(
                name=name,
                required=required,
                found=path is not None,
                note=note,
            )
        )
    return results


def _check_env_vars(env: str, environ: Mapping[str, str]) -> list[EnvVarStatus]:
    statuses: list[EnvVarStatus] = []
    if env in ("nonprod", "prod"):
        bucket = environ.get("STATE_BUCKET", "").strip()
        statuses.append(
            EnvVarStatus(
                name="STATE_BUCKET",
                required=True,
                configured=bool(bucket),
                valid=bool(bucket),
                detail="Configured S3 state bucket" if bucket else "Missing S3 backend bucket name",
            )
        )

        op_arn = environ.get("TF_VAR_operator_role_arn", "").strip()
        op_valid = bool(IAM_ROLE_ARN_RE.match(op_arn))
        statuses.append(
            EnvVarStatus(
                name="TF_VAR_operator_role_arn",
                required=True,
                configured=bool(op_arn),
                valid=op_valid,
                detail=(
                    "Valid IAM role ARN (routine operator access defaults to AmazonEKSViewPolicy)"
                    if op_valid
                    else (
                        "Must be an IAM role ARN (arn:aws:iam::<12-digit>:role/...), not an IAM user or STS session ARN"
                        if op_arn
                        else "Missing routine operator IAM role ARN"
                    )
                ),
            )
        )

        cidrs_raw = environ.get("TF_VAR_operator_access_cidrs", "").strip()
        if cidrs_raw:
            cidr_valid, cidr_detail = _validate_cidrs(cidrs_raw)
        else:
            cidr_valid, cidr_detail = False, "Missing JSON list of routed private IPv4 CIDRs (exclude /0)"
        statuses.append(
            EnvVarStatus(
                name="TF_VAR_operator_access_cidrs",
                required=True,
                configured=bool(cidrs_raw),
                valid=cidr_valid,
                detail=cidr_detail,
            )
        )

        budget_raw = environ.get("TF_VAR_budget", "").strip()
        budget_required = env == "prod"
        if budget_raw:
            budget_valid, budget_detail = _validate_budget_var(budget_raw)
        elif budget_required:
            budget_valid, budget_detail = (
                False,
                "REQUIRED in prod (`envs/prod` enforces non-null monthly AWS Budget)",
            )
        else:
            budget_valid, budget_detail = (
                True,
                "Optional in nonprod (recommended alongside shared bootstrap AWS Budget)",
            )
        statuses.append(
            EnvVarStatus(
                name="TF_VAR_budget",
                required=budget_required,
                configured=bool(budget_raw),
                valid=budget_valid,
                detail=budget_detail,
            )
        )

        bg_arn = environ.get("TF_VAR_break_glass_role_arn", "").strip()
        if not bg_arn:
            bg_valid = True
            bg_detail = (
                "Optional in Terraform, but required during initial `bootstrap-argocd.sh` or emergency "
                "recovery (`AmazonEKSClusterAdminPolicy`) because `TF_VAR_operator_role_arn` defaults to `AmazonEKSViewPolicy`"
            )
        elif not IAM_ROLE_ARN_RE.match(bg_arn):
            bg_valid = False
            bg_detail = "Invalid IAM role ARN format for TF_VAR_break_glass_role_arn"
        elif op_arn and bg_arn == op_arn:
            bg_valid = False
            bg_detail = "TF_VAR_break_glass_role_arn must be distinct from TF_VAR_operator_role_arn"
        else:
            bg_valid = True
            bg_detail = "Valid distinct break-glass admin IAM role ARN (`AmazonEKSClusterAdminPolicy`)"
        statuses.append(
            EnvVarStatus(
                name="TF_VAR_break_glass_role_arn",
                required=False,
                configured=bool(bg_arn),
                valid=bg_valid,
                detail=bg_detail,
            )
        )
        return statuses

    if env == "gke":
        for var_name, desc in [
            ("TF_VAR_project_id", "Billing-enabled GCP project ID (or set in envs/gke/lab.secret.tfvars)"),
            ("TF_VAR_operator_member", "IAM member user:email or group:email (or set in lab.secret.tfvars)"),
            ("TF_VAR_operator_access_cidrs", "JSON list of routed private CIDRs excluding /0"),
        ]:
            raw = environ.get(var_name, "").strip()
            if var_name == "TF_VAR_operator_access_cidrs" and raw:
                valid, detail = _validate_cidrs(raw)
            else:
                valid = bool(raw)
                detail = "Configured" if valid else f"Not set in environment ({desc})"
            statuses.append(
                EnvVarStatus(
                    name=var_name,
                    required=True,
                    configured=bool(raw),
                    valid=valid,
                    detail=detail,
                )
            )
        return statuses

    if env == "aks":
        for var_name, desc in [
            ("TF_VAR_subscription_id", "Azure subscription UUID (or set in envs/aks/lab.secret.tfvars)"),
            ("TF_VAR_tenant_id", "Microsoft Entra tenant UUID (or set in envs/aks/lab.secret.tfvars)"),
            ("TF_VAR_operator_group_object_id", "Entra admin group object UUID (or set in envs/aks/lab.secret.tfvars)"),
        ]:
            raw = environ.get(var_name, "").strip()
            valid = bool(raw)
            statuses.append(
                EnvVarStatus(
                    name=var_name,
                    required=True,
                    configured=valid,
                    valid=valid,
                    detail="Configured" if valid else f"Not set in environment ({desc})",
                )
            )
        return statuses

    raise ValueError(f"Unsupported environment: {env}")


def _verify_cloud_identity(
    env: str,
    which: Callable[[str], str | None],
    environ: Mapping[str, str],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> IdentityStatus:
    if env in ("nonprod", "prod"):
        if which("aws") is None:
            return IdentityStatus(
                requested=True,
                verified=False,
                detail="Cannot run `aws sts get-caller-identity`: `aws` CLI not found in PATH",
            )
        cmd = ["aws"]
        profile = environ.get("EKS_OPERATOR_PROFILE", "").strip()
        if profile:
            cmd.extend(["--profile", profile])
        cmd.extend(["sts", "get-caller-identity", "--output", "json"])
        try:
            proc = runner(
                cmd,
                env=dict(environ),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return IdentityStatus(
                requested=True,
                verified=False,
                detail=f"AWS STS check failed: {mask_identifiers(str(exc))}",
            )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "nonzero exit").strip().splitlines()[0]
            return IdentityStatus(
                requested=True,
                verified=False,
                detail=f"AWS STS check exited {proc.returncode}: {mask_identifiers(err)}",
            )
        return IdentityStatus(
            requested=True,
            verified=True,
            detail="Authenticated AWS caller verified via STS (account and ARN redacted)",
        )

    if env == "gke":
        if which("gcloud") is None:
            return IdentityStatus(
                requested=True,
                verified=False,
                detail="Cannot verify GCP identity: `gcloud` CLI not found in PATH",
            )
        try:
            proc = runner(
                ["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
                env=dict(environ),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return IdentityStatus(requested=True, verified=False, detail=f"gcloud check failed: {exc}")
        ok = proc.returncode == 0 and bool(proc.stdout.strip())
        return IdentityStatus(
            requested=True,
            verified=ok,
            detail="Active gcloud identity verified" if ok else "No active gcloud account found",
        )

    if which("az") is None:
        return IdentityStatus(
            requested=True,
            verified=False,
            detail="Cannot verify Azure identity: `az` CLI not found in PATH",
        )
    try:
        proc = runner(
            ["az", "account", "show", "--output", "json"],
            env=dict(environ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return IdentityStatus(requested=True, verified=False, detail=f"az account check failed: {exc}")
    ok = proc.returncode == 0
    return IdentityStatus(
        requested=True,
        verified=ok,
        detail="Active Azure subscription verified" if ok else "Azure CLI session not authenticated",
    )


def evaluate_preflight(
    env: str = "nonprod",
    hours: float | str | Decimal = Decimal("2.0"),
    *,
    verify_identity: bool = False,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> PreflightReport:
    """Evaluate local tooling, environment variables, private API caveats, and Decimal costs."""
    hours_dec = parse_hours(hours)
    env_map = os.environ if environ is None else environ

    tools = _check_tools(env, which)
    env_vars = _check_env_vars(env, env_map)
    region, cost_items, comparison_notes = estimate_costs(env, hours_dec)

    if verify_identity:
        identity = _verify_cloud_identity(env, which, env_map, runner=runner)
    else:
        identity = IdentityStatus(
            requested=False,
            verified=None,
            detail="NOT RUN (offline mode; pass --verify-identity to query live cloud credentials)",
        )

    blockers: list[str] = []
    for tool in tools:
        if tool.required and not tool.found:
            blockers.append(f"Missing required CLI tool in PATH: `{tool.name}`")
    for var in env_vars:
        if var.required and not var.valid:
            blockers.append(f"Environment variable `{var.name}`: {var.detail}")
        elif not var.required and var.configured and not var.valid:
            blockers.append(f"Invalid optional environment variable `{var.name}`: {var.detail}")
    if verify_identity and not identity.verified:
        blockers.append(f"Cloud identity check failed: {identity.detail}")

    total_hourly = sum((item.hourly_usd for item in cost_items), Decimal("0"))
    total_session = (total_hourly * hours_dec).quantize(CENT, rounding=ROUND_HALF_UP)
    total_30d = (total_hourly * HOURS_PER_30_DAYS).quantize(CENT, rounding=ROUND_HALF_UP)

    private_api_warning = (
        "Private Kubernetes API reachability: cluster control-plane endpoints disable public access "
        "(`endpoint_public_access = false` on EKS, `enable_private_endpoint = true` on GKE, "
        "`private_cluster_enabled = true` on AKS). Terraform AWS API calls can run over HTTPS, "
        "but `bootstrap-argocd.sh`, `helm`, `kubectl`, and `kubeseal` require a routed VPC network "
        "path (SSM session host, bastion, or VPN) with private DNS resolution matching `operator_access_cidrs`."
    )

    free_tier_cautions = [
        (
            "Free Tier does NOT imply $0 lab cost: AWS EKS Standard support bills $0.10/cluster/hour, "
            "and `m6i.large` workers, NAT Gateways ($0.059/hr + per-GB data), KMS keys, CloudWatch Logs, "
            "and gp3 EBS volumes accrue charges unless covered by verified, active promotional credits."
        ),
        (
            "AWS Budgets sends email/SNS alerts when forecasted or actual spend crosses thresholds; "
            "it is NOT an automatic spending cap and does not terminate running clusters."
        ),
        (
            "Before `terraform destroy`, remove Kubernetes-provisioned LoadBalancers and check "
            "`Retain`-policy EBS PVCs (such as production Prometheus) so orphaned cloud disks and EIPs "
            "do not continue billing."
        ),
    ]

    return PreflightReport(
        env=env,
        region=region,
        hours=hours_dec,
        generated_utc=datetime.now(timezone.utc).isoformat(),
        ready=len(blockers) == 0,
        tools=tools,
        env_vars=env_vars,
        identity=identity,
        cost_items=cost_items,
        total_hourly_usd=total_hourly,
        total_session_usd=total_session,
        total_monthly_30d_usd=total_30d,
        comparison_notes=comparison_notes,
        private_api_warning=private_api_warning,
        free_tier_cautions=free_tier_cautions,
        blockers=blockers,
    )


def render_markdown(report: PreflightReport) -> str:
    readiness = "READY" if report.ready else f"ACTION REQUIRED ({len(report.blockers)} blocker(s))"
    lines = [
        f"# Cloud Lab Preflight — `{report.env}` ({report.region})",
        "",
        f"- **Generated (UTC):** `{report.generated_utc}`",
        f"- **Planned session window:** `{report.hours}` hour(s)",
        f"- **Overall readiness:** **{readiness}**",
        f"- **Identity verification:** {report.identity.detail}",
        "",
        "## 1. Local CLI Tooling",
        "",
        "| Tool | Required | Status | Purpose |",
        "| --- | --- | --- | --- |",
    ]
    for tool in report.tools:
        status = "FOUND" if tool.found else "MISSING"
        req = "Yes" if tool.required else "Optional"
        lines.append(f"| `{tool.name}` | {req} | **{status}** | {tool.note} |")

    lines.extend([
        "",
        "## 2. Environment & Access Variables",
        "",
        "| Variable | Required | Status | Notes |",
        "| --- | --- | --- | --- |",
    ])
    for var in report.env_vars:
        if var.configured and var.valid:
            status = "OK"
        elif var.configured and not var.valid:
            status = "INVALID"
        elif var.required:
            status = "MISSING"
        else:
            status = "UNSET (OPTIONAL)"
        req = "Yes" if var.required else "Optional"
        lines.append(f"| `{var.name}` | {req} | **{status}** | {mask_identifiers(var.detail)} |")

    lines.extend([
        "",
        "## 3. Private Control-Plane Reachability Warning",
        "",
        f"> **Warning:** {report.private_api_warning}",
        "",
        f"## 4. Itemized Regional Cost Estimate (`{report.region}`, `Decimal` USD)",
        "",
        f"| Component | Baseline specification | Hourly rate | {report.hours}h session | 30-day (720h) run-rate |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for item in report.cost_items:
        lines.append(
            f"| {item.component} | {item.spec} | {format_hourly_usd(item.hourly_usd)} | "
            f"{format_usd(item.session_usd)} | {format_usd(item.monthly_30d_usd)} |"
        )
    lines.append(
        f"| **Estimated baseline total** | Fixed infrastructure floor (excl. per-GB egress/logs/KMS API) | "
        f"**{format_hourly_usd(report.total_hourly_usd)}** | "
        f"**{format_usd(report.total_session_usd)}** | "
        f"**{format_usd(report.total_monthly_30d_usd)}** |"
    )

    lines.extend(["", "### Architecture & Sizing Notes", ""])
    for note in report.comparison_notes:
        lines.append(f"- {note}")

    lines.extend(["", "## 5. Free Tier & Billing Guardrails", ""])
    for caution in report.free_tier_cautions:
        lines.append(f"- {caution}")

    if report.blockers:
        lines.extend(["", "## 6. Blocking Prerequisites Before Live Provisioning", ""])
        for blocker in report.blockers:
            lines.append(f"- {mask_identifiers(blocker)}")

    return "\n".join(lines) + "\n"


def render_json(report: PreflightReport) -> str:
    payload = {
        "env": report.env,
        "region": report.region,
        "hours": str(report.hours),
        "generated_utc": report.generated_utc,
        "ready": report.ready,
        "identity": {
            "requested": report.identity.requested,
            "verified": report.identity.verified,
            "detail": mask_identifiers(report.identity.detail),
        },
        "tools": [
            {
                "name": t.name,
                "required": t.required,
                "found": t.found,
                "note": t.note,
            }
            for t in report.tools
        ],
        "env_vars": [
            {
                "name": v.name,
                "required": v.required,
                "configured": v.configured,
                "valid": v.valid,
                "detail": mask_identifiers(v.detail),
            }
            for v in report.env_vars
        ],
        "cost_estimate": {
            "currency": "USD",
            "hourly_usd": f"{report.total_hourly_usd.quantize(HOURLY_PRECISION, rounding=ROUND_HALF_UP):.4f}",
            "session_usd": f"{report.total_session_usd.quantize(CENT, rounding=ROUND_HALF_UP):.2f}",
            "monthly_30d_usd": f"{report.total_monthly_30d_usd.quantize(CENT, rounding=ROUND_HALF_UP):.2f}",
            "items": [
                {
                    "component": item.component,
                    "spec": item.spec,
                    "hourly_usd": f"{item.hourly_usd.quantize(HOURLY_PRECISION, rounding=ROUND_HALF_UP):.4f}",
                    "session_usd": f"{item.session_usd.quantize(CENT, rounding=ROUND_HALF_UP):.2f}",
                    "monthly_30d_usd": f"{item.monthly_30d_usd.quantize(CENT, rounding=ROUND_HALF_UP):.2f}",
                }
                for item in report.cost_items
            ],
            "comparison_notes": report.comparison_notes,
        },
        "private_api_warning": report.private_api_warning,
        "free_tier_cautions": report.free_tier_cautions,
        "blockers": [mask_identifiers(b) for b in report.blockers],
    }
    return json.dumps(payload, indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env",
        choices=("nonprod", "prod", "gke", "aks"),
        default="nonprod",
        help="Target cloud lab environment root (default: nonprod)",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=2.0,
        help="Planned lab duration in hours for session cost estimation (default: 2.0)",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--verify-identity",
        action="store_true",
        help="Query live cloud CLI identity (e.g., aws sts get-caller-identity); default is zero-network offline mode",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero (code 1) when any required prerequisite or requested identity check fails",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        hours_dec = parse_hours(args.hours)
    except ValueError as exc:
        parser.error(str(exc))

    report = evaluate_preflight(
        env=args.env,
        hours=hours_dec,
        verify_identity=args.verify_identity,
    )
    output = render_json(report) if args.format == "json" else render_markdown(report)
    sys.stdout.write(output)
    if (args.strict or args.verify_identity) and not report.ready:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
