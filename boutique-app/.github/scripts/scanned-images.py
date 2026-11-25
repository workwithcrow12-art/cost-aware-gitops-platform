import argparse
import json
from pathlib import Path
import re


SERVICES = (
    "adservice",
    "cartservice",
    "checkoutservice",
    "currencyservice",
    "emailservice",
    "frontend",
    "loadgenerator",
    "paymentservice",
    "productcatalogservice",
    "recommendationservice",
    "shippingservice",
)
ENVIRONMENTS = ("dev", "staging", "prod", "preview")
LOADGENERATOR_ENVIRONMENTS = {"dev", "staging"}
UPSTREAM = "us-central1-docker.pkg.dev/online-boutique-ci/microservices-demo"
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
TOP_LEVEL_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+:")
IMAGES_HEADER_RE = re.compile(r"^images:[ \t]*(?:\[[ \t]*\])?[ \t]*(?:#.*)?$")
FINOPS_IMAGE_LINE_RE = re.compile(
    r"^([ \t]*image:[ \t]*)ghcr\.io/[a-z0-9-]+/finops-toolkit"
    r"(?::[^ \t@#]+)?(?:@sha256:[0-9a-f]{64})?([ \t]*(?:#.*)?)$"
)


def load_service_digests(
    records_dir: Path,
    revision: str,
    parser: argparse.ArgumentParser,
) -> dict[str, str]:
    expected = {f"scanned-image-{service}" for service in SERVICES}
    if not records_dir.is_dir() or {path.name for path in records_dir.iterdir()} != expected:
        parser.error("The scanned records must contain the complete service set")

    digests: dict[str, str] = {}
    for service in SERVICES:
        directory = records_dir / f"scanned-image-{service}"
        path = directory / f"{service}.json"
        if not directory.is_dir() or {file.name for file in directory.iterdir()} != {path.name}:
            parser.error(f"Invalid artifact contents in {directory.name}")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            parser.error(f"Invalid {path.name}: {error}")
        if (
            not isinstance(record, dict)
            or set(record) != {"revision", "digest"}
            or record["revision"] != revision
            or not isinstance(record["digest"], str)
            or not DIGEST_RE.fullmatch(record["digest"])
        ):
            parser.error(f"Invalid revision or digest in {path.name}")
        digests[service] = record["digest"]
    return digests


def load_finops_digest(
    record_path: Path,
    revision: str,
    parser: argparse.ArgumentParser,
) -> str:
    if not record_path.is_file():
        parser.error(f"Missing FinOps digest record: {record_path}")
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        parser.error(f"Invalid {record_path.name}: {error}")
    allowed_keys = {"revision", "digest", "tag", "image"}
    if (
        not isinstance(record, dict)
        or not ({"revision", "digest"} <= set(record) <= allowed_keys)
        or record["revision"] != revision
        or not isinstance(record["digest"], str)
        or not DIGEST_RE.fullmatch(record["digest"])
        or ("tag" in record and (not isinstance(record["tag"], str) or not record["tag"]))
        or ("image" in record and (not isinstance(record["image"], str) or not record["image"]))
    ):
        parser.error(f"Invalid FinOps revision or digest in {record_path.name}")
    return record["digest"]


def update_overlay_kustomization(
    kustomization_path: Path,
    owner: str,
    selected_services: list[tuple[str, str]],
    parser: argparse.ArgumentParser,
) -> None:
    if not kustomization_path.is_file():
        parser.error(f"Missing overlay kustomization: {kustomization_path}")
    try:
        lines = kustomization_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        parser.error(f"Unable to read {kustomization_path}: {error}")

    images_block = ["images:"]
    for service, digest in selected_services:
        images_block.extend(
            [
                f"  - name: {UPSTREAM}/{service}",
                f"    newName: ghcr.io/{owner}/{service}",
                f"    digest: {digest}",
            ]
        )

    header_indices = [idx for idx, line in enumerate(lines) if IMAGES_HEADER_RE.match(line)]
    if len(header_indices) > 1:
        parser.error(f"Multiple images blocks found in {kustomization_path}")

    if header_indices:
        start = header_indices[0]
        end = start + 1
        while end < len(lines):
            line = lines[end]
            if line.startswith((" ", "\t")):
                end += 1
                continue
            if line.strip() == "" or line.startswith("#"):
                lookahead = end + 1
                while lookahead < len(lines) and (
                    lines[lookahead].strip() == "" or lines[lookahead].startswith("#")
                ):
                    lookahead += 1
                if lookahead < len(lines) and lines[lookahead].startswith((" ", "\t")):
                    end = lookahead + 1
                    continue
                break
            if TOP_LEVEL_KEY_RE.match(line) or line.startswith("---"):
                break
            end += 1
        updated_lines = lines[:start] + images_block + lines[end:]
    else:
        while lines and lines[-1].strip() == "":
            lines.pop()
        updated_lines = lines + images_block

    while updated_lines and updated_lines[-1].strip() == "":
        updated_lines.pop()
    kustomization_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8", newline="\n")


def update_finops_cronjob(
    cronjob_path: Path,
    owner: str,
    digest: str,
    parser: argparse.ArgumentParser,
) -> None:
    if not cronjob_path.is_file():
        parser.error(f"Missing FinOps CronJob manifest: {cronjob_path}")
    try:
        lines = cronjob_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        parser.error(f"Unable to read {cronjob_path}: {error}")

    matches = 0
    updated_lines: list[str] = []
    for line in lines:
        match = FINOPS_IMAGE_LINE_RE.match(line)
        if match:
            matches += 1
            updated_lines.append(f"{match.group(1)}ghcr.io/{owner}/finops-toolkit@{digest}{match.group(2)}")
        else:
            updated_lines.append(line)

    if matches != 1:
        parser.error(f"Expected exactly one finops-toolkit image reference in {cronjob_path}")
    while updated_lines and updated_lines[-1].strip() == "":
        updated_lines.pop()
    cronjob_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GitOps image replacements from scanned image records")
    parser.add_argument("records", type=Path)
    parser.add_argument("owner")
    parser.add_argument("revision")
    parser.add_argument("environment", choices=ENVIRONMENTS)
    parser.add_argument(
        "--apply-gitops",
        type=Path,
        default=None,
        help="Optional gitops-config root directory to update overlay kustomization in place",
    )
    parser.add_argument(
        "--finops-record",
        type=Path,
        default=None,
        help="Optional finops-toolkit JSON digest record to pin in platform/finops-reporter/cronjob.yaml",
    )
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z0-9-]+", args.owner) or not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("Invalid registry owner or source revision")
    if args.finops_record is not None and args.apply_gitops is None:
        parser.error("--finops-record requires --apply-gitops")

    digests = load_service_digests(args.records, args.revision, parser)
    include_loadgenerator = args.environment in LOADGENERATOR_ENVIRONMENTS
    selected_services = [
        (service, digests[service])
        for service in SERVICES
        if include_loadgenerator or service != "loadgenerator"
    ]
    images = [
        f"{UPSTREAM}/{service}=ghcr.io/{args.owner}/{service}@{digest}"
        for service, digest in selected_services
    ]

    if args.apply_gitops is not None:
        finops_digest = None
        if args.finops_record is not None:
            finops_digest = load_finops_digest(args.finops_record, args.revision, parser)
        overlay_path = args.apply_gitops / "apps" / "boutique" / "overlays" / args.environment / "kustomization.yaml"
        update_overlay_kustomization(overlay_path, args.owner, selected_services, parser)
        if finops_digest is not None:
            cronjob_path = args.apply_gitops / "platform" / "finops-reporter" / "cronjob.yaml"
            update_finops_cronjob(cronjob_path, args.owner, finops_digest, parser)

    print(json.dumps({"images": images}, indent=2))


if __name__ == "__main__":
    main()
