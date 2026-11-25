"""Preview or record timestamped, secret-redacted AWS cloud lab execution evidence."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Sequence


SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import cloud_lab_preflight as preflight  # noqa: E402


ARN_RE = re.compile(
    r"arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:(?:[0-9]{12}|aws)?:[^\s\"'`<>,)\]]+"
)
ACCOUNT_ID_RE = re.compile(r"(?<![0-9a-fA-F])[0-9]{12}(?![0-9a-fA-F])")
AWS_ACCESS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b")
GITHUB_TOKEN_RE = re.compile(
    r"\b(?:(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
)
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*")
AUTH_HEADER_RE = re.compile(
    r"(?i)(authorization\s*[:=]\s*(?:bearer|token|basic)\s+)([^\s\"',;]+)"
)
SECRET_KV_RE = re.compile(
    r"(?i)\b((?:aws_secret_access_key|aws_session_token|secret_access_key|session_token|"
    r"client_secret|webhook_url|api_key|access_token|refresh_token|password|passwd|secret|token)"
    r"\s*[:=]\s*[\"']?)(?![A-Za-z0-9_]+\s*[:=])(?!<REDACTED_)([^\s\"',;]+)([\"']?)"
)


@dataclass(frozen=True)
class RunbookStage:
    stage_id: str
    title: str
    preview_commands: tuple[str, ...]
    executable_group: str | None = None


@dataclass(frozen=True)
class StageExecutionStep:
    stage_id: str
    log_name: str
    command: Sequence[str]


@dataclass(frozen=True)
class StageEvidence:
    stage_id: str
    title: str
    started_utc: str
    ended_utc: str
    revision: str
    status: str


def redact_sensitive_text(text: str) -> str:
    """Redact AWS account IDs, ARNs, access keys, bearer tokens, JWTs, and secrets."""
    redacted = ARN_RE.sub("<REDACTED_ARN>", text)
    redacted = AWS_ACCESS_KEY_RE.sub("<REDACTED_AWS_KEY_ID>", redacted)
    redacted = GITHUB_TOKEN_RE.sub("<REDACTED_TOKEN>", redacted)
    redacted = JWT_RE.sub("<REDACTED_TOKEN>", redacted)
    redacted = AUTH_HEADER_RE.sub(r"\1<REDACTED_TOKEN>", redacted)
    redacted = SECRET_KV_RE.sub(r"\1<REDACTED_SECRET>\3", redacted)
    redacted = ACCOUNT_ID_RE.sub("<REDACTED_ACCOUNT_ID>", redacted)
    return redacted


def detect_git_revision(cwd: Path = ROOT) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "UNKNOWN"


def build_runbook_stages(env: str, base_url: str = "http://localhost:8080") -> list[RunbookStage]:
    namespace = "boutique-prod" if env == "prod" else "boutique-dev"
    budget_export = (
        ["export TF_VAR_budget='{\"monthly_limit_usd\":500,\"email\":\"finops@example.com\"}'"]
        if env == "prod"
        else []
    )
    stages = [
        RunbookStage(
            stage_id="preflight",
            title="Identity, preflight & Decimal cost check",
            preview_commands=(
                f"python scripts/cloud_lab_preflight.py --env {env} --hours 2 --verify-identity --strict",
            ),
            executable_group="preflight",
        ),
        RunbookStage(
            stage_id="terraform-plan-apply",
            title=f"State backend & Terraform plan/apply ({env})",
            preview_commands=tuple([
                "cd platform-infra",
                "export STATE_BUCKET=\"$(terraform -chdir=bootstrap/state-backend output -raw state_bucket_name)\"",
                "export STATE_BUCKET_REGION=\"$(terraform -chdir=bootstrap/state-backend output -raw state_bucket_region)\"",
                "export TF_VAR_operator_role_arn='arn:aws:iam::<ACCOUNT_ID>:role/ClusterOperator'",
                "export TF_VAR_break_glass_role_arn='arn:aws:iam::<ACCOUNT_ID>:role/ClusterBreakGlassAdmin'",
                "export TF_VAR_operator_access_cidrs='[\"10.20.1.0/24\"]'",
                *budget_export,
                f"make plan ENV={env}",
                f"make apply ENV={env}",
            ]),
        ),
        RunbookStage(
            stage_id="argocd-bootstrap",
            title="Private EKS API Argo CD bootstrap (break-glass admin role)",
            preview_commands=(
                "cd platform-infra",
                "export EKS_OPERATOR_PROFILE='break-glass-admin'",
                f"bash scripts/bootstrap-argocd.sh {env} ../gitops-config",
                "kubectl -n argocd get applications,applicationsets",
            ),
        ),
        RunbookStage(
            stage_id="smoke",
            title=f"Pre-drill rollout & storefront checkout smoke ({namespace})",
            preview_commands=(
                f"kubectl -n {namespace} get rollouts,analysisruns,pods",
                f"python boutique-app/.github/scripts/smoke-checkout.py --base-url {base_url}",
            ),
            executable_group="smoke",
        ),
    ]
    if env == "nonprod":
        stages.append(
            RunbookStage(
                stage_id="canary-drill",
                title="Canary fault injection & AnalysisRun abort check (boutique-dev only)",
                preview_commands=(
                    "# Via reviewed GitOps PR on dev overlay, set candidate PRODUCT_CATALOG_SERVICE_ADDR=missing-catalog:3550",
                    "kubectl -n boutique-dev get rollouts,analysisruns,pods",
                ),
            )
        )
    else:
        stages.append(
            RunbookStage(
                stage_id="canary-drill",
                title="Canary fault injection drill (skipped in prod; run in nonprod/dev only)",
                preview_commands=(
                    "# Fault-injection drills target nonprod boutique-dev; production sync remains manual.",
                ),
            )
        )
    stages.extend([
        RunbookStage(
            stage_id="rollback-verify",
            title="Git revert rollback & post-rollback checkout smoke",
            preview_commands=(
                "git revert <bad-promotion-commit>",
                f"kubectl -n {namespace} get rollouts,analysisruns,pods",
                f"python boutique-app/.github/scripts/smoke-checkout.py --base-url {base_url}",
            ),
        ),
        RunbookStage(
            stage_id="teardown",
            title="Kubernetes LB/PVC cleanup & Terraform destroy",
            preview_commands=(
                f"kubectl -n {namespace} get svc,pvc",
                f"cd platform-infra && make destroy ENV={env}",
            ),
        ),
        RunbookStage(
            stage_id="billing-reconciliation",
            title="Post-run residual resource & AWS Billing verification",
            preview_commands=(
                "aws ec2 describe-nat-gateways --region ap-southeast-1",
                "aws ec2 describe-volumes --region ap-southeast-1",
            ),
        ),
    ])
    return stages


def default_execution_steps(
    env: str,
    execute_stage: str,
    base_url: str = "http://localhost:8080",
) -> list[StageExecutionStep]:
    namespace = "boutique-prod" if env == "prod" else "boutique-dev"
    steps: list[StageExecutionStep] = []
    if execute_stage in ("preflight", "all"):
        steps.append(
            StageExecutionStep(
                stage_id="preflight",
                log_name="preflight.log",
                command=[
                    sys.executable,
                    str(SCRIPTS_DIR / "cloud_lab_preflight.py"),
                    "--env",
                    env,
                    "--verify-identity",
                    "--strict",
                ],
            )
        )
    if execute_stage in ("smoke", "all"):
        steps.extend([
            StageExecutionStep(
                stage_id="smoke",
                log_name="cluster-workloads.log",
                command=["kubectl", "-n", namespace, "get", "rollouts,analysisruns,pods"],
            ),
            StageExecutionStep(
                stage_id="smoke",
                log_name="smoke-checkout.log",
                command=[
                    sys.executable,
                    str(ROOT / "boutique-app/.github/scripts/smoke-checkout.py"),
                    "--base-url",
                    base_url,
                ],
            ),
        ])
    return steps


def _render_readiness_plan(
    env: str,
    mode_label: str,
    revision: str,
    preflight_md: str,
    stages: Sequence[RunbookStage],
) -> str:
    lines = [
        f"# AWS Cloud Lab Readiness & Execution Plan (`{env}`)",
        "",
        f"- **Generated (UTC):** `{datetime.now(timezone.utc).isoformat()}`",
        f"- **Mode:** `{mode_label}`",
        f"- **Source Git revision:** `{redact_sensitive_text(revision)}`",
        "",
        "## Runbook Stage Sequence",
        "",
    ]
    for index, stage in enumerate(stages, start=1):
        lines.append(f"### Stage {index}: {stage.title} (`{stage.stage_id}`)")
        lines.append("")
        lines.append("```bash")
        lines.extend(stage.preview_commands)
        lines.append("```")
        lines.append("")

    lines.extend([
        "---",
        "",
        preflight_md.rstrip(),
        "",
    ])
    return "\n".join(lines)


def _render_evidence_markdown(
    env: str,
    dry_run: bool,
    revision: str,
    rows: Sequence[StageEvidence],
) -> str:
    banner = (
        "Mode: **DRY RUN** — no cloud commands were executed and no AWS resources were queried or created. "
        "All stages are recorded as `NOT RUN (DRY RUN)`."
        if dry_run
        else "Mode: **LIVE STAGE EXECUTION** — only explicitly requested stages ran; sensitive account IDs, ARNs, and tokens are redacted from logs."
    )
    lines = [
        f"# AWS Cloud Lab Evidence Record (`{env}`)",
        "",
        f"- **Recorded (UTC):** `{datetime.now(timezone.utc).isoformat()}`",
        f"- **Source Git revision:** `{redact_sensitive_text(revision)}`",
        f"- {banner}",
        "",
        "| Stage | UTC Start -> End | Commit / Digest | Result / Evidence Log |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        window = "—" if row.started_utc == "—" else f"`{row.started_utc}` -> `{row.ended_utc}`"
        lines.append(
            f"| {row.title} | {window} | `{redact_sensitive_text(row.revision)}` | {row.status} |"
        )
    lines.extend([
        "",
        "Measure recovery time from failed candidate detection to successful post-rollback checkout; "
        "keep continuous stable-pod availability separate from Git desired-state restoration time.",
        "",
    ])
    return "\n".join(lines)


def run_lab(
    output: Path,
    *,
    env: str = "nonprod",
    dry_run: bool = True,
    execute_stage: str | None = None,
    hours: float | Decimal = Decimal("2.0"),
    base_url: str = "http://localhost:8080",
    steps: Sequence[StageExecutionStep] | None = None,
    revision: str | None = None,
) -> int:
    """Write dry-run readiness/evidence files or execute non-destructive verification stages."""
    output.mkdir(parents=True, exist_ok=False)
    rev = revision if revision is not None else detect_git_revision(ROOT)
    stages = build_runbook_stages(env=env, base_url=base_url)

    pf_report = preflight.evaluate_preflight(env=env, hours=hours, verify_identity=False)
    pf_markdown = preflight.render_markdown(pf_report)

    if dry_run or execute_stage is None:
        plan_md = _render_readiness_plan(
            env=env,
            mode_label="DRY RUN (preview only; zero live cloud commands)",
            revision=rev,
            preflight_md=pf_markdown,
            stages=stages,
        )
        rows = [
            StageEvidence(
                stage_id=stage.stage_id,
                title=stage.title,
                started_utc="—",
                ended_utc="—",
                revision=rev if rev != "UNKNOWN" else "—",
                status="NOT RUN (DRY RUN)",
            )
            for stage in stages
        ]
        evidence_md = _render_evidence_markdown(env=env, dry_run=True, revision=rev, rows=rows)
        (output / "readiness-plan.md").write_text(plan_md, encoding="utf-8")
        (output / "evidence-template.md").write_text(evidence_md, encoding="utf-8")
        print(f"DRY RUN: wrote readiness-plan.md and evidence-template.md to {output}")
        return 0

    active_steps = list(steps) if steps is not None else default_execution_steps(env, execute_stage, base_url)
    plan_md = _render_readiness_plan(
        env=env,
        mode_label=f"EXECUTE STAGE ({execute_stage})",
        revision=rev,
        preflight_md=pf_markdown,
        stages=stages,
    )
    (output / "readiness-plan.md").write_text(plan_md, encoding="utf-8")

    environment = dict(os.environ)
    environment.update(
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
    )

    stage_results: dict[str, StageEvidence] = {}
    exit_code = 0

    for step in active_steps:
        started = datetime.now(timezone.utc).isoformat()
        try:
            proc = subprocess.run(
                list(step.command),
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                timeout=120,
            )
            code, raw_log = proc.returncode, proc.stdout
        except subprocess.TimeoutExpired as exc:
            partial = exc.output or b""
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", errors="replace")
            code, raw_log = 1, partial + "\n" + str(exc) + "\n"
        except OSError as exc:
            code, raw_log = 1, str(exc) + "\n"
        ended = datetime.now(timezone.utc).isoformat()

        display_cmd = (
            ["python", *step.command[1:]]
            if step.command and step.command[0] == sys.executable
            else list(step.command)
        )
        header = (
            f"# Command: {shlex.join(display_cmd)}\n"
            f"# Started (UTC): {started}\n"
            f"# Ended (UTC): {ended}\n"
            f"# Exit code: {code}\n\n"
        )
        redacted_log = redact_sensitive_text(header + raw_log)
        (output / step.log_name).write_text(redacted_log, encoding="utf-8")

        stage_title = next(
            (s.title for s in stages if s.stage_id == step.stage_id),
            step.stage_id,
        )
        prior = stage_results.get(step.stage_id)
        first_start = prior.started_utc if prior is not None else started
        if code == 0:
            prior_logs = (
                f"{prior.status}, `{step.log_name}`"
                if prior is not None and prior.status.startswith("PASS")
                else f"PASS (`{step.log_name}`)"
            )
            status_text = prior_logs
        else:
            status_text = f"FAIL (exit {code}; see `{step.log_name}`)"

        stage_results[step.stage_id] = StageEvidence(
            stage_id=step.stage_id,
            title=stage_title,
            started_utc=first_start,
            ended_utc=ended,
            revision=rev,
            status=status_text,
        )
        print(f"{'PASS' if code == 0 else f'FAIL (exit {code})'}: {step.log_name}")
        if code != 0:
            exit_code = code if code != 0 else 1
            break

    known_stage_ids = {s.stage_id for s in stages}
    evidence_rows: list[StageEvidence] = []
    for stage in stages:
        if stage.stage_id in stage_results:
            evidence_rows.append(stage_results[stage.stage_id])
        else:
            evidence_rows.append(
                StageEvidence(
                    stage_id=stage.stage_id,
                    title=stage.title,
                    started_utc="—",
                    ended_utc="—",
                    revision=rev if rev != "UNKNOWN" else "—",
                    status="NOT RUN",
                )
            )
    for stage_id, custom_row in stage_results.items():
        if stage_id not in known_stage_ids:
            evidence_rows.append(custom_row)

    evidence_md = _render_evidence_markdown(
        env=env,
        dry_run=False,
        revision=rev,
        rows=evidence_rows,
    )
    (output / "evidence-template.md").write_text(evidence_md, encoding="utf-8")
    print(f"Evidence: {output}")
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env",
        choices=("nonprod", "prod"),
        default="nonprod",
        help="AWS EKS environment target (default: nonprod)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / ".scratch" / ("aws-lab-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")),
        help="New evidence directory; existing directories are never overwritten",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview runbook stages and write NOT RUN (DRY RUN) evidence without running cloud commands (default)",
    )
    parser.add_argument(
        "--execute-stage",
        choices=("preflight", "smoke", "all"),
        default=None,
        help="Explicitly execute live verification stage(s) and record redacted logs",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=2.0,
        help="Planned session hours for embedded preflight cost estimate (default: 2.0)",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080",
        help="Port-forwarded storefront URL for the smoke stage (default: http://localhost:8080)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.dry_run and args.execute_stage is not None:
        parser.error("--dry-run cannot be combined with --execute-stage")
    try:
        hours_dec = preflight.parse_hours(args.hours)
    except ValueError as exc:
        parser.error(str(exc))

    is_dry_run = args.execute_stage is None
    try:
        return run_lab(
            args.output_dir.resolve(),
            env=args.env,
            dry_run=is_dry_run,
            execute_stage=args.execute_stage,
            hours=hours_dec,
            base_url=args.base_url,
        )
    except FileExistsError:
        parser.error("output directory already exists; choose a new path to preserve its evidence")


if __name__ == "__main__":
    raise SystemExit(main())
