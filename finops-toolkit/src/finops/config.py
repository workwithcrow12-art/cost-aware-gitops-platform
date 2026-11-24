import re
from dataclasses import dataclass
from os import environ

_IDENTIFIER = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


def required(key: str) -> str:
    value = environ.get(key, "").strip()
    if not value:
        raise ValueError(f"Set {key} to use this mode")
    return value


def _optional_column(key: str, default: str) -> str | None:
    raw = environ.get(key)
    if raw is None:
        return default
    value = raw.strip()
    if not value or value.lower() == "none":
        return None
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{key} must be a valid Athena column identifier or 'none'")
    return value


def _bool_env(key: str, *, default: bool) -> bool:
    raw = environ.get(key, "").strip().lower()
    if not raw:
        return default
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    raise ValueError(f"{key} must be true or false")


@dataclass(frozen=True)
class AthenaConfig:
    region: str
    database: str
    table: str
    workgroup: str
    output_s3: str
    partitioned: bool = True
    env_tag_column: str | None = "resource_tags_user_env"
    team_tag_column: str | None = "resource_tags_user_team"

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
            partitioned=_bool_env("ATHENA_PARTITIONED", default=True),
            env_tag_column=_optional_column("ATHENA_ENV_TAG_COLUMN", "resource_tags_user_env"),
            team_tag_column=_optional_column("ATHENA_TEAM_TAG_COLUMN", "resource_tags_user_team"),
        )
