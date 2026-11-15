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
UPSTREAM = "us-central1-docker.pkg.dev/online-boutique-ci/microservices-demo"


def main():
    parser = argparse.ArgumentParser(description="Build GitOps image replacements from scanned image records")
    parser.add_argument("records", type=Path)
    parser.add_argument("owner")
    parser.add_argument("revision")
    parser.add_argument("environment", choices=("dev", "preview"))
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z0-9-]+", args.owner) or not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("Invalid registry owner or source revision")
    expected = {f"scanned-image-{service}" for service in SERVICES}
    if not args.records.is_dir() or {path.name for path in args.records.iterdir()} != expected:
        parser.error("The scanned records must contain the complete service set")

    images = []
    for service in SERVICES:
        directory = args.records / f"scanned-image-{service}"
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
            or record["revision"] != args.revision
            or not isinstance(record["digest"], str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", record["digest"])
        ):
            parser.error(f"Invalid revision or digest in {path.name}")
        if args.environment == "dev" or service != "loadgenerator":
            images.append(f"{UPSTREAM}/{service}=ghcr.io/{args.owner}/{service}@{record['digest']}")

    print(json.dumps({"images": images}, indent=2))


if __name__ == "__main__":
    main()
