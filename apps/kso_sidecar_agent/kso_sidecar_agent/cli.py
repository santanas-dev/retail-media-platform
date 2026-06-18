"""KSO Sidecar Agent CLI — skeleton only.

Commands:
    version             Show version
    init-local-root     Create folder structure + agent_status.json
    doctor              Check folder + agent_status.json + config health
    set-status          Update agent status
    write-config        Create/update agent config
    config-status       Show config health
    secret-store-check  Check dev secret store
    secret-store-set    Write dev secret (stdin only)
    secret-store-delete Delete dev secret
    auth-check          Check device auth (safe summary only)

This is a SKELETON. No backend calls, no secrets, no media sync yet.
"""

import argparse
import sys

from kso_sidecar_agent import (
    agent_status, device_auth_client, local_config, local_file_store, safe_logger,
    secret_store,
)
from kso_sidecar_agent.http_client import HttpClientConfig, SafeHttpClient
from kso_sidecar_agent.retry_backoff import BackoffPolicy, RetryBackoffManager

try:
    from importlib.metadata import version as _version
    VERSION = _version("kso-sidecar-agent")
except Exception:
    VERSION = "0.1.0"


def cmd_version(args: argparse.Namespace) -> None:
    print(f"kso-sidecar-agent {VERSION}")


def cmd_init_local_root(args: argparse.Namespace) -> None:
    root = args.root
    local_file_store.init_local_root(root)
    print(f"Initialized agent root at: {root}")
    safe_logger.log(level="info", event="init_local_root",
                    message="Agent root initialized", extra={"root": root})


def cmd_doctor(args: argparse.Namespace) -> None:
    result = local_file_store.doctor(args.root, dev_secret_store=args.dev_secret_store)

    print(f"Doctor check for: {args.root}")
    print(f"  root_exists:       {result['root_exists']}")
    print(f"  folders_ok:        {result['folders_ok']}")
    print(f"  total_folders:     {result['total_folders']}")
    missing = result.get("missing_folders", [])
    print(f"  missing_folders:   {len(missing)}")
    for m in missing:
        print(f"    - {m}")

    print(f"  agent_status_ok:   {result['agent_status_ok']}")
    if result.get("agent_status_error"):
        print(f"  agent_status_error: {result['agent_status_error']}")
    if result.get("agent_status"):
        print(f"  agent_status:      {result['agent_status']}")

    print(f"  config_ok:         {result['config_ok']}")
    if result.get("config_error"):
        print(f"  config_error:      {result['config_error']}")
    if result.get("config_details"):
        d = result["config_details"]
        print(f"  backend:           {d.get('backend_scheme', '')}://{d.get('backend_host', '')}")
        print(f"  device_code:       {d.get('device_code', '')}")

    # Dev secret store
    if result.get("dev_secret_store_checked"):
        ds = result["dev_secret_store"]
        print(f"  dev_secret_store:  present={ds['present']}, permissions_ok={ds['permissions_ok']}")
        if ds.get("warning"):
            print(f"  dev_secret_warn:   {ds['warning']}")

    all_ok = (result["root_exists"] and result["folders_ok"]
              and result["agent_status_ok"] and result["config_ok"])
    if all_ok:
        print("\n✓ All checks passed.")
    else:
        print("\n✗ Issues found.\n  Run 'init-local-root' + 'write-config' to set up.")
        sys.exit(1)


def cmd_set_status(args: argparse.Namespace) -> None:
    try:
        errors = args.error if args.error else []
        data = agent_status.update_status(
            root=args.root, status=args.status,
            offline_mode=args.offline_mode,
            cached_items=args.cached_items,
            invalid_hash_items=args.invalid_hash_items,
            errors=errors,
        )
        print(f"Status updated: {data['status']}")
        print(f"  updated_at:       {data['updated_at']}")
        print(f"  offline_mode:     {data['offline_mode']}")
        print(f"  cached_items:     {data['cached_items']}")
        print(f"  invalid_hash_items: {data['invalid_hash_items']}")
        if data["errors"]:
            print(f"  errors:           {len(data['errors'])}")
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_write_config(args: argparse.Namespace) -> None:
    try:
        data = {
            "backend_base_url": args.backend_base_url,
            "device_code": args.device_code,
            "tls_verify": args.tls_verify,
            "request_timeout_sec": args.request_timeout_sec,
            "local_interface_version": args.local_interface_version,
        }
        validated = local_config.write_config(args.root, data)
        print(f"Config written to: {args.root}/config/agent_config.json")
        parsed = validated["backend_base_url"]
        print(f"  backend:          {parsed}")
        print(f"  device_code:      {validated['device_code']}")
        print(f"  tls_verify:       {validated['tls_verify']}")
        print(f"  timeout_sec:      {validated['request_timeout_sec']}")
        print(f"  interface_ver:    {validated['local_interface_version']}")
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config_status(args: argparse.Namespace) -> None:
    result = local_config.config_status(args.root)
    if not result["present"]:
        print("Config: MISSING (no config/agent_config.json)")
        print("  Run 'write-config' to create one.")
        return

    if not result["ok"]:
        print("Config: INVALID")
        print(f"  Error: {result['error']}")
        sys.exit(1)

    print("Config: PRESENT (valid)")
    print(f"  backend:          {result['backend_scheme']}://{result['backend_host']}")
    print(f"  device_code:      {result['device_code']}")
    print(f"  tls_verify:       {result['tls_verify']}")
    print(f"  timeout_sec:      {result['request_timeout_sec']}")
    print(f"  interface_ver:    {result['local_interface_version']}")


# ── Secret store commands ─────────────────────────────────────────

def cmd_secret_store_check(args: argparse.Namespace) -> None:
    """Check dev secret store status (never prints secret value)."""
    try:
        result = secret_store.check_secret_store(args.root, args.dev_secret_store)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print("Secret store: dev-only")
    print(f"  present:          {result['present']}")
    perms = result["permissions_ok"]
    if perms is None:
        perms = "unknown (not supported on this OS)"
    print(f"  permissions_ok:   {perms}")
    print(f"  readable_by_agent: {result['readable_by_agent']}")


def cmd_secret_store_set(args: argparse.Namespace) -> None:
    """Write secret from stdin. Never prints or logs the secret."""
    try:
        if not args.stdin:
            print("ERROR: Secret must be provided via stdin with --stdin flag.",
                  file=sys.stderr)
            sys.exit(1)

        raw = sys.stdin.read()
        secret_store.write_secret(args.root, raw, args.dev_secret_store)
        print("Secret stored (dev-only).")
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_secret_store_delete(args: argparse.Namespace) -> None:
    """Delete dev secret store file."""
    try:
        deleted = secret_store.delete_secret(args.root, args.dev_secret_store)
        if deleted:
            print("Secret deleted.")
        else:
            print("Secret store: already absent.")
    except (ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


# ── Auth commands ─────────────────────────────────────────────────


def cmd_auth_check(args: argparse.Namespace) -> None:
    """Check device auth — prints only safe summary, never token/secret."""
    try:
        # ── Read config ─────────────────────────────────────────────
        cfg = local_config.read_config(args.root)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: Config — {e}", file=sys.stderr)
        sys.exit(1)

    try:
        # ── Secret reader ───────────────────────────────────────────
        dev_flag = args.dev_secret_store
        def _read_secret() -> str:
            return secret_store.read_secret(args.root, dev_secret_store=dev_flag)

        # Verify secret is readable
        secret = _read_secret()
        if not secret:
            print("ERROR: Device secret is empty. Run 'secret-store-set' first.", file=sys.stderr)
            sys.exit(1)

        # ── Build HTTP client ───────────────────────────────────────
        http_config = HttpClientConfig(
            base_url=cfg["backend_base_url"],
            timeout_sec=cfg.get("request_timeout_sec", 10),
            tls_verify=cfg.get("tls_verify", True),
        )
        http_client = SafeHttpClient(http_config)

        # ── Build auth client ───────────────────────────────────────
        auth = device_auth_client.DeviceAuthClient(
            http_client=http_client,
            config=cfg,
            secret_reader=_read_secret,
        )

        # ── Build retry manager (optional) ──────────────────────────
        retry_manager = None
        if args.retry_auth:
            policy = BackoffPolicy(max_attempts=args.auth_max_attempts)
            retry_manager = RetryBackoffManager(policy)

        # ── Auth ────────────────────────────────────────────────────
        token_state = auth.authenticate(retry_manager=retry_manager)

        # ── Print safe summary (no token!) ──────────────────────────
        summary = token_state.safe_summary()
        print(f"authenticated:     {summary['authenticated']}")
        print(f"device_code:       {summary['device_code']}")
        print(f"device_id:         {summary['device_id']}")
        print(f"status:            {summary['status']}")
        print(f"expires_in_sec:    {summary['expires_in_sec']}")
        print(f"attempts:          {auth.last_attempts}")

    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except device_auth_client.HttpClientError as e:
        print(f"ERROR: Auth failed — {e}", file=sys.stderr)
        print(f"retryable:         {e.retryable}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected — {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kso-agent",
        description="KSO Sidecar Agent — skeleton. No backend calls yet.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # version
    p_ver = sub.add_parser("version", help="Show version")
    p_ver.set_defaults(func=cmd_version)

    # init-local-root
    p_init = sub.add_parser("init-local-root", help="Create folder structure")
    p_init.add_argument("--root", required=True, help="Root path")
    p_init.set_defaults(func=cmd_init_local_root)

    # doctor
    p_doc = sub.add_parser("doctor", help="Check folder + status + config health")
    p_doc.add_argument("--root", required=True, help="Root path")
    p_doc.add_argument("--dev-secret-store", action="store_true", default=False,
                       help="Check dev secret store")
    p_doc.set_defaults(func=cmd_doctor)

    # set-status
    p_ss = sub.add_parser("set-status", help="Update agent status")
    p_ss.add_argument("--root", required=True, help="Root path")
    p_ss.add_argument("--status", required=True,
                      choices=sorted(agent_status.ALLOWED_STATUSES), help="Agent status")
    p_ss.add_argument("--offline-mode", type=str, default="false")
    p_ss.add_argument("--cached-items", type=int, default=0)
    p_ss.add_argument("--invalid-hash-items", type=int, default=0)
    p_ss.add_argument("--error", action="append", default=[])
    p_ss.set_defaults(func=cmd_set_status)

    # write-config
    p_wc = sub.add_parser("write-config", help="Create/update agent config")
    p_wc.add_argument("--root", required=True, help="Root path")
    p_wc.add_argument("--backend-base-url", required=True)
    p_wc.add_argument("--device-code", required=True)
    p_wc.add_argument("--tls-verify", type=str, default="true")
    p_wc.add_argument("--request-timeout-sec", type=int, default=10)
    p_wc.add_argument("--local-interface-version", type=str, default="1.0")
    p_wc.set_defaults(func=cmd_write_config)

    # config-status
    p_cs = sub.add_parser("config-status", help="Show config health")
    p_cs.add_argument("--root", required=True, help="Root path")
    p_cs.set_defaults(func=cmd_config_status)

    # ── Secret store commands ──────────────────────────────────────

    p_sc = sub.add_parser("secret-store-check", help="Check dev secret store")
    p_sc.add_argument("--root", required=True, help="Root path")
    p_sc.add_argument("--dev-secret-store", action="store_true", default=False,
                      help="Enable dev secret store")
    p_sc.set_defaults(func=cmd_secret_store_check)

    p_ss_set = sub.add_parser("secret-store-set", help="Write secret from stdin")
    p_ss_set.add_argument("--root", required=True, help="Root path")
    p_ss_set.add_argument("--dev-secret-store", action="store_true", default=False,
                          help="Enable dev secret store")
    p_ss_set.add_argument("--stdin", action="store_true", default=False,
                          help="Read secret from stdin")
    p_ss_set.set_defaults(func=cmd_secret_store_set)

    p_ss_del = sub.add_parser("secret-store-delete", help="Delete dev secret")
    p_ss_del.add_argument("--root", required=True, help="Root path")
    p_ss_del.add_argument("--dev-secret-store", action="store_true", default=False,
                          help="Enable dev secret store")
    p_ss_del.set_defaults(func=cmd_secret_store_delete)

    # ── Auth commands ──────────────────────────────────────────────

    p_auth = sub.add_parser("auth-check", help="Check device auth (safe summary only)")
    p_auth.add_argument("--root", required=True, help="Root path")
    p_auth.add_argument("--dev-secret-store", action="store_true", default=False,
                        help="Read secret from dev secret store")
    p_auth.add_argument("--retry-auth", action="store_true", default=False,
                        help="Enable retry with exponential backoff")
    p_auth.add_argument("--auth-max-attempts", type=int, default=3,
                        help="Max auth attempts when --retry-auth (default: 3)")
    p_auth.set_defaults(func=cmd_auth_check)

    args = parser.parse_args()

    # Convert string bools
    for attr in ("offline_mode", "tls_verify"):
        if hasattr(args, attr) and isinstance(getattr(args, attr), str):
            setattr(args, attr, getattr(args, attr).lower() in ("true", "1", "yes"))

    args.func(args)


if __name__ == "__main__":
    main()
