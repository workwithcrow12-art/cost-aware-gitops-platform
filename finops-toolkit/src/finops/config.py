from dataclasses import dataclass
from os import environ


def required(key: str) -> str:
    value = environ.get(key, "").strip()
    if not value:
        raise ValueError(f"Set {key} to use this mode")
    return value


@dataclass(frozen=True)
class AthenaConfig:
    region: str
    database: str
    table: str
    workgroup: str
    output_s3: str

    @classmethod
    def from_environment(cls) -> "AthenaConfig | None":
        if not environ.get("ATHENA_TABLE", "").strip():
            return None
        return cls(
            required("AWS_REGION"),
            required("ATHENA_DATABASE"),
            required("ATHENA_TABLE"),
            required("ATHENA_WORKGROUP"),
            required("ATHENA_OUTPUT_S3"),
        )
