"""Configuration: one YAML file, no secrets in it.

The gateway token and the Postgres password are resolved through `gateway_token()` and
`postgres_password()` every time they are needed, so short-lived credentials keep working.
Those two functions are the only places to change when authentication moves to a service
principal or OAuth.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
THINKING_LEVELS = ("off", "low", "medium", "high")


class Section(dict):
    """A dict with attribute access, so config reads as cfg.ledger.lease_s."""

    def __getattr__(self, name: str) -> Any:
        try:
            v = self[name]
        except KeyError as e:
            raise AttributeError(name) from e
        return Section(v) if isinstance(v, dict) and not isinstance(v, Section) else v


def _wrap(v: Any) -> Any:
    if isinstance(v, dict):
        return Section({k: _wrap(x) for k, x in v.items()})
    if isinstance(v, list):
        return [_wrap(x) for x in v]
    return v


def config_path() -> Path:
    p = os.environ.get("DOC_ENGINE_CONFIG")
    if p:
        return Path(p)
    return ROOT / "config.yaml"


def load_config(path: str | Path | None = None) -> Section:
    p = Path(path) if path else config_path()
    if not p.exists():
        raise SystemExit(f"config file not found: {p}\nCopy config.example.yaml to config.yaml and fill it in, "
                         f"or set DOC_ENGINE_CONFIG.")
    cfg = _wrap(yaml.safe_load(p.read_text()) or {})
    cfg["_path"] = str(p)
    # Environment overrides, so a deployment can run from the example file with no edits.
    if os.environ.get("DOC_ENGINE_GATEWAY_URL"):
        cfg["gateway"]["base_url"] = os.environ["DOC_ENGINE_GATEWAY_URL"]
    if os.environ.get("DOC_ENGINE_TOKEN_SOURCE"):
        cfg["gateway"]["token_source"] = os.environ["DOC_ENGINE_TOKEN_SOURCE"]
    if os.environ.get("DOC_ENGINE_PG_PASSWORD_SOURCE"):
        cfg["postgres"]["password_source"] = os.environ["DOC_ENGINE_PG_PASSWORD_SOURCE"]
    problems = validate(cfg)
    if problems:
        raise SystemExit("config problems in " + str(p) + ":\n  - " + "\n  - ".join(problems))
    return cfg


def validate(cfg: Section) -> list[str]:
    out: list[str] = []
    for sec in ("gateway", "models", "ledger", "worker", "postgres", "server"):
        if sec not in cfg:
            out.append(f"missing section: {sec}")
    if out:
        return out
    if not cfg.models:
        out.append("models: at least one model is required")
    for key, m in cfg.models.items():
        for f in ("gateway_name", "itpm", "otpm", "bucket_capacity_output", "pricing"):
            if f not in m:
                out.append(f"models.{key}.{f} is missing")
        if m.get("thinking_off", "disabled") not in ("disabled", "between_tools", "effort_low"):
            out.append(f"models.{key}.thinking_off must be disabled, between_tools or effort_low")
        for f in ("input", "output", "cache_read", "cache_write"):
            if not isinstance((m.get("pricing") or {}).get(f), (int, float)):
                out.append(f"models.{key}.pricing.{f} must be a number (USD per million tokens)")
    for where, allowed in (("ledger.capacity_mode", ("fixed", "duration")),
                           ("gateway.streaming", ("auto", "always", "never")),
                           ("gateway.token_source", ("env", "databricks_oauth")),
                           ("worker.send_images_as", ("image", "pdf")),
                           ("postgres.password_source", ("env", "databricks_oauth"))):
        sec, name = where.split(".")
        v = cfg[sec].get(name)
        if v is not None and str(v).lower() not in allowed:
            out.append(f"{where} is {v!r}; it must be " + " or ".join(allowed))
    try:
        margin = float(cfg.ledger.get("safety_margin_fraction", 0.05))
        if not 0 <= margin < 1:
            out.append(f"ledger.safety_margin_fraction is {margin}; it must be 0 or more and below 1")
    except (TypeError, ValueError):
        out.append("ledger.safety_margin_fraction must be a number")
    if float(cfg.ledger.get("lease_s", 900)) <= float(cfg.gateway.get("request_timeout_s", 600)):
        out.append("ledger.lease_s must exceed gateway.request_timeout_s")
    if int(cfg.gateway.get("max_connections", 512)) <= int(cfg.worker.get("concurrency", 128)):
        out.append("gateway.max_connections must exceed worker.concurrency")
    return out


def placeholders(cfg: Section) -> list[str]:
    """FILL-IN values still present. Reported by preflight; not fatal for commands that do not need them."""
    out = []
    if "FILL-IN" in str(cfg.gateway.get("base_url", "")):
        out.append("gateway.base_url")
    # A Postgres value left at FILL-IN is taken from its standard variable, as postgres_conninfo does.
    for k, env in (("host", "PGHOST"), ("dbname", "PGDATABASE"), ("user", "PGUSER")):
        if "FILL-IN" in str(cfg.postgres.get(k, "")) and not os.environ.get(env):
            out.append(f"postgres.{k}")
    return out


def databricks_oauth_token() -> str:
    """The app's own OAuth token (its service principal) on Databricks Apps. Refreshed by the SDK.
    Not exercised outside Databricks: confirm in the first deployment."""
    global _workspace
    if _workspace is None:
        from databricks.sdk import WorkspaceClient  # available in the Databricks Apps runtime
        _workspace = WorkspaceClient()     # kept: the SDK reuses a token until it is close to expiry
    return _workspace.config.oauth_token().access_token


_workspace: Any = None


def gateway_token(cfg: Section) -> str:
    if str(cfg.gateway.get("token_source", "env")).lower() == "databricks_oauth":
        return databricks_oauth_token()
    name = cfg.gateway.get("token_env_var", "DATABRICKS_TOKEN")
    tok = os.environ.get(name, "")
    if not tok:
        raise RuntimeError(f"environment variable {name} is not set (gateway token)")
    return tok


def postgres_password(cfg: Section) -> str | None:
    if str(cfg.postgres.get("password_source", "env")).lower() == "databricks_oauth":
        return databricks_oauth_token()
    cmd = cfg.postgres.get("password_command") or ""
    if cmd:
        return subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True).stdout.strip()
    name = cfg.postgres.get("password_env_var") or "PGPASSWORD"
    return os.environ.get(name) or None


def postgres_conninfo(cfg: Section) -> dict[str, Any]:
    pg = cfg.postgres

    def pick(key: str, env: str, default: Any = None) -> Any:
        v = pg.get(key)
        if v in (None, "", "FILL-IN"):
            v = os.environ.get(env, default)
        return v

    info = {
        "host": pick("host", "PGHOST"),
        "port": pick("port", "PGPORT", 5432),
        "dbname": pick("dbname", "PGDATABASE"),
        "user": pick("user", "PGUSER"),
        "sslmode": pick("sslmode", "PGSSLMODE", "require"),
        "application_name": "doc_engine",
    }
    pw = postgres_password(cfg)
    if pw:
        info["password"] = pw
    return {k: v for k, v in info.items() if v not in (None, "")}


def model_cfg(cfg: Section, model: str) -> Section:
    if model not in cfg.models:
        raise KeyError(f"model {model!r} is not configured (configured: {', '.join(cfg.models)})")
    return cfg.models[model]


def public_models(cfg: Section) -> list[dict[str, Any]]:
    out = []
    for key, m in cfg.models.items():
        out.append({
            "key": key, "label": m.get("label", key), "gateway_name": m.gateway_name,
            "itpm": m.itpm, "otpm": m.otpm, "pricing": dict(m.pricing),
            "thinking_off": m.get("thinking_off", "disabled"),
            "out_capacity": effective_out_capacity(cfg, key),
        })
    return out


def effective_out_capacity(cfg: Section, model: str) -> float:
    m = model_cfg(cfg, model)
    margin = float(cfg.ledger.get("safety_margin_fraction", 0.05))
    cap = float(m.get("bucket_capacity_output") or m.otpm)
    return cap * (1 - margin)
