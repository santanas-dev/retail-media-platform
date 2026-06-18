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
    runtime-config-status Show runtime config health
    sync-runtime-config Full runtime config sync: auth→fetch→save
    heartbeat-once      Send a single heartbeat
    manifest-status     Show local manifest health
    sync-manifest        Sync manifest: auth→fetch→save
    auth-check          Check device auth (safe summary only)

This is a SKELETON. No backend calls, no secrets, no media sync yet.
"""

import argparse
import sys
from pathlib import Path

from kso_sidecar_agent import (
    agent_status, device_auth_client, heartbeat_client, local_config,
    local_file_store, manifest_store, media_cache, runtime_config_store, safe_logger, secret_store,
)
from kso_sidecar_agent.http_client import HttpClientConfig, HttpClientError, SafeHttpClient
from kso_sidecar_agent.manifest_client import ManifestClient
from kso_sidecar_agent.media_client import MediaClient
from kso_sidecar_agent.retry_backoff import BackoffPolicy, RetryBackoffManager
from kso_sidecar_agent.runtime_config_client import RuntimeConfigClient

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

    # Runtime config
    print(f"  runtime_config_ok: {result['runtime_config_ok']}")
    if result.get("runtime_config_error"):
        print(f"  runtime_config_err: {result['runtime_config_error']}")

    # Manifest
    print(f"  manifest_ok:       {result['manifest_ok']}")
    if result.get("manifest_error"):
        print(f"  manifest_error:    {result['manifest_error']}")
    elif result.get("manifest_details"):
        d = result["manifest_details"]
        print(f"  manifest_present:  {d.get('present')}")
        if d.get("present"):
            print(f"  manifest_items:    {d.get('items_count')}")

    # Media cache
    if result.get("media_cache_details"):
        cd = result["media_cache_details"]
        print(f"  media_cache_ok:    {result.get('media_cache_ok', True)}")
        print(f"  cache_items_total: {cd.get('items_total')}")
        print(f"  cache_items_cached:{cd.get('items_cached')}")
        if cd.get("items_missing", 0) > 0:
            print(f"  cache_missing:     {cd['items_missing']}")
        if cd.get("items_invalid_hash", 0) > 0:
            print(f"  cache_invalid_hash:{cd['items_invalid_hash']}")
    elif result.get("media_cache_issues"):
        for issue in result["media_cache_issues"]:
            print(f"  media_cache_issue: {issue}")

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


# ── Runtime config commands ────────────────────────────────────────


def cmd_runtime_config_status(args: argparse.Namespace) -> None:
    """Show runtime_config.json health (never prints full config)."""
    result = runtime_config_store.runtime_config_status(args.root)
    if not result["present"]:
        print("Runtime config: MISSING (no config/runtime_config.json)")
        return

    if not result["ok"]:
        print("Runtime config: INVALID")
        print(f"  Error: {result['error']}")
        sys.exit(1)

    print("Runtime config: PRESENT (valid)")
    print(f"  config_hash:       {result.get('config_hash', '')[:12]}...")
    print(f"  etag_present:      {result.get('etag_present')}")
    print(f"  generated_at:      {result.get('generated_at')}")
    print(f"  fetched_at:        {result.get('fetched_at')}")
    print(f"  config_keys_count: {result.get('config_keys_count')}")


def cmd_sync_runtime_config(args: argparse.Namespace) -> None:
    """Full runtime config sync: auth → fetch → save. Never prints token/secret."""
    # ── 1. Read config ─────────────────────────────────────────────
    try:
        cfg = local_config.read_config(args.root)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: Config — {e}", file=sys.stderr)
        sys.exit(1)

    try:
        # ── 2. Secret reader ──────────────────────────────────────
        dev_flag = args.dev_secret_store
        def _read_secret() -> str:
            return secret_store.read_secret(args.root, dev_secret_store=dev_flag)

        secret = _read_secret()
        if not secret:
            print("ERROR: Device secret is empty.", file=sys.stderr)
            sys.exit(1)

        # ── 3. HTTP client ─────────────────────────────────────────
        http_config = HttpClientConfig(
            base_url=cfg["backend_base_url"],
            timeout_sec=cfg.get("request_timeout_sec", 10),
            tls_verify=cfg.get("tls_verify", True),
        )
        http_client = SafeHttpClient(http_config)

        # ── 4. Auth ────────────────────────────────────────────────
        retry_manager = None
        if args.retry_auth:
            policy = BackoffPolicy(max_attempts=args.auth_max_attempts)
            retry_manager = RetryBackoffManager(policy)

        auth = device_auth_client.DeviceAuthClient(
            http_client=http_client,
            config=cfg,
            secret_reader=_read_secret,
        )
        token_state = auth.authenticate(retry_manager=retry_manager)

        # ── 5. Existing ETag ───────────────────────────────────────
        existing_etag = None
        try:
            existing = runtime_config_store.read_runtime_config(args.root)
            existing_etag = existing.get("etag")
        except (FileNotFoundError, ValueError):
            pass  # no local file or invalid — fetch fresh

        # ── 6. Fetch runtime config ────────────────────────────────
        rc_client = RuntimeConfigClient(http_client=http_client)
        snapshot = rc_client.fetch_current(token_state, etag=existing_etag)

        # ── 7. Save ────────────────────────────────────────────────
        store_result = runtime_config_store.write_runtime_config(args.root, snapshot)

        # ── 8. Safe output ─────────────────────────────────────────
        if snapshot.not_modified:
            print("runtime_config_sync: not_modified")
            print(f"etag_present:       {existing_etag is not None}")
        else:
            print("runtime_config_sync: updated")
            summary = snapshot.safe_summary()
            print(f"config_hash:        {summary['config_hash']}")
            print(f"config_keys_count:  {summary['config_keys_count']}")

    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except device_auth_client.HttpClientError as e:
        print(f"ERROR: Runtime config sync failed — {e}", file=sys.stderr)
        print(f"retryable:          {e.retryable}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected — {e}", file=sys.stderr)
        sys.exit(1)


# ── Heartbeat commands ─────────────────────────────────────────────


def cmd_heartbeat_once(args: argparse.Namespace) -> None:
    """Send a single heartbeat. Never prints token/secret."""
    try:
        cfg = local_config.read_config(args.root)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: Config — {e}", file=sys.stderr)
        sys.exit(1)

    try:
        # ── Secret ────────────────────────────────────────────────
        dev_flag = args.dev_secret_store
        def _read_secret() -> str:
            return secret_store.read_secret(args.root, dev_secret_store=dev_flag)

        secret = _read_secret()
        if not secret:
            print("ERROR: Device secret is empty.", file=sys.stderr)
            sys.exit(1)

        # ── HTTP client ───────────────────────────────────────────
        http_config = HttpClientConfig(
            base_url=cfg["backend_base_url"],
            timeout_sec=cfg.get("request_timeout_sec", 10),
            tls_verify=cfg.get("tls_verify", True),
        )
        http_client = SafeHttpClient(http_config)

        # ── Auth ──────────────────────────────────────────────────
        retry_manager = None
        if args.retry_auth:
            policy = BackoffPolicy(max_attempts=args.auth_max_attempts)
            retry_manager = RetryBackoffManager(policy)

        auth = device_auth_client.DeviceAuthClient(
            http_client=http_client, config=cfg, secret_reader=_read_secret,
        )
        token_state = auth.authenticate(retry_manager=retry_manager)

        # ── Build payload ─────────────────────────────────────────
        payload = heartbeat_client.HeartbeatPayload(
            status=args.status,
            message=args.message,
            app_version=args.app_version,
            os_version=args.os_version,
            storage_free_mb=args.storage_free_mb,
            cache_items_count=args.cache_items_count,
            current_manifest_hash=args.current_manifest_hash,
        )

        # ── Send heartbeat ────────────────────────────────────────
        hb_retry = None
        if args.retry_heartbeat:
            hb_policy = BackoffPolicy(max_attempts=args.heartbeat_max_attempts)
            hb_retry = RetryBackoffManager(hb_policy)

        hb = heartbeat_client.HeartbeatClient(
            http_client=http_client, retry_manager=hb_retry,
        )
        result = hb.send_heartbeat(token_state, payload)

        # ── Safe output ───────────────────────────────────────────
        attempts = auth.last_attempts
        print(f"heartbeat:         sent")
        print(f"status:            {payload.status}")
        print(f"backend_status:    {result.backend_status or 'accepted'}")
        print(f"attempts:          {attempts}")

    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: Invalid payload — {e}", file=sys.stderr)
        sys.exit(1)
    except heartbeat_client.HttpClientError as e:
        print(f"ERROR: Heartbeat failed — {e}", file=sys.stderr)
        print(f"retryable:         {e.retryable}", file=sys.stderr)
        print(f"attempts:          {auth.last_attempts}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected — {e}", file=sys.stderr)
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


# ── Manifest commands ──────────────────────────────────────────────

def cmd_manifest_status(args: argparse.Namespace) -> None:
    """Show local manifest status — reads only local file, no backend.

    Never prints full manifest or local_path.
    """
    try:
        status = manifest_store.manifest_store_status(args.root)
    except Exception as e:
        print(f"ERROR: Cannot read manifest — {e}", file=sys.stderr)
        sys.exit(1)

    if not status["present"]:
        print("Manifest: MISSING (no manifest/current_manifest.json)")
        print("  Run 'sync-manifest' once implemented to fetch from backend.")
        return

    if status["validation_status"] == "error":
        print("Manifest: INVALID")
        print(f"  File exists but fails validation.")
        sys.exit(1)

    print("Manifest: PRESENT (valid)")
    print(f"  version_id:        {status['manifest_version_id']}")
    print(f"  hash:              {status['manifest_hash']}")
    print(f"  source:            {status['source']}")
    print(f"  generated_at:      {status['generated_at']}")
    print(f"  fetched_at:        {status['fetched_at']}")
    print(f"  items_count:       {status['items_count']}")


# ── Media cache status command ──────────────────────────────────────

def cmd_media_cache_status(args: argparse.Namespace) -> None:
    """Show local media cache status. No backend calls, no token/secret."""
    root = Path(args.root)

    # Try to read manifest for detailed status
    manifest_items = None
    try:
        manifest = manifest_store.read_current_manifest(root)
        manifest_items = manifest.get("items", [])
    except (FileNotFoundError, ValueError, Exception):
        pass  # no manifest — show basic status

    status = media_cache.media_cache_status(root, manifest_items=manifest_items)

    print(f"Media cache status for: {args.root}")

    if manifest_items is not None:
        print(f"  items_total:       {status['items_total']}")
        print(f"  items_cached:      {status['items_cached']}")
        print(f"  items_missing:     {status['items_missing']}")
        print(f"  invalid_hash:      {status['items_invalid_hash']}")
        print(f"  invalid_size:      {status['items_invalid_size']}")
        print(f"  cache_complete:    {status['cache_complete']}")
    else:
        print(f"  present:           {status['present']}")
        print(f"  current_files:     {status['current_files_count']}")
        print(f"  staging_files:     {status['staging_files_count']}")
        print(f"  quarantine_files:  {status['quarantine_files_count']}")

    if manifest_items is not None and not status.get("cache_complete"):
        issues = []
        if status.get("items_missing", 0) > 0:
            issues.append(f"{status['items_missing']} missing")
        if status.get("items_invalid_hash", 0) > 0:
            issues.append(f"{status['items_invalid_hash']} invalid hash")
        if status.get("items_invalid_size", 0) > 0:
            issues.append(f"{status['items_invalid_size']} size mismatch")
        print(f"  issues:            {', '.join(issues)}")


# ── Manifest sync commands ─────────────────────────────────────────

def cmd_sync_manifest(args: argparse.Namespace) -> None:
    """Full manifest sync: auth → fetch manifest → save locally. Never prints token/secret."""
    # ── 1. Read config ─────────────────────────────────────────────
    try:
        cfg = local_config.read_config(args.root)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: Config — {e}", file=sys.stderr)
        sys.exit(1)

    try:
        # ── 2. Secret reader ──────────────────────────────────────
        dev_flag = args.dev_secret_store
        def _read_secret() -> str:
            return secret_store.read_secret(args.root, dev_secret_store=dev_flag)

        secret = _read_secret()
        if not secret:
            print("ERROR: Device secret is empty.", file=sys.stderr)
            sys.exit(1)

        # ── 3. HTTP client ─────────────────────────────────────────
        http_config = HttpClientConfig(
            base_url=cfg["backend_base_url"],
            timeout_sec=cfg.get("request_timeout_sec", 10),
            tls_verify=cfg.get("tls_verify", True),
        )
        http_client = SafeHttpClient(http_config)

        # ── 4. Auth ────────────────────────────────────────────────
        retry_manager = None
        if args.retry_auth:
            policy = BackoffPolicy(max_attempts=args.auth_max_attempts)
            retry_manager = RetryBackoffManager(policy)

        auth = device_auth_client.DeviceAuthClient(
            http_client=http_client,
            config=cfg,
            secret_reader=_read_secret,
        )
        token_state = auth.authenticate(retry_manager=retry_manager)

        # ── 5. Fetch manifest ─────────────────────────────────────
        mc = ManifestClient(http_client=http_client)
        snapshot = mc.fetch_current(token_state)

        # ── 6. Write locally ───────────────────────────────────────
        result = manifest_store.write_current_manifest(args.root, snapshot)

        # ── 7. Safe output ─────────────────────────────────────────
        if result["status"] == "not_modified":
            print("manifest_sync:        not_modified")
            # Check if local file exists
            local_present = False
            try:
                manifest_store.read_current_manifest(args.root)
                local_present = True
            except (FileNotFoundError, ValueError):
                pass
            print(f"local_manifest_present: {str(local_present).lower()}")
        elif result["status"] == "no_manifest":
            print("manifest_sync:        no_manifest")
            local_present = False
            try:
                manifest_store.read_current_manifest(args.root)
                local_present = True
            except (FileNotFoundError, ValueError):
                pass
            print(f"local_manifest_present: {str(local_present).lower()}")
        else:
            print("manifest_sync:        updated")
            mvid = result.get("manifest_version_id", "")
            if len(mvid) > 12:
                mvid = mvid[:12] + "..."
            print(f"manifest_version_id:  {mvid}")
            print(f"manifest_hash:       {snapshot.manifest_hash[:12] if snapshot.manifest_hash else 'N/A'}...")
            print(f"items_count:         {result['items_count']}")

    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except HttpClientError as e:
        print(f"ERROR: Manifest sync failed — {e}", file=sys.stderr)
        print(f"retryable:           {e.retryable}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: Manifest validation — {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected — {e}", file=sys.stderr)
        sys.exit(1)


# ── Media sync command ───────────────────────────────────────────────

def cmd_sync_media(args: argparse.Namespace) -> None:
    """Full media sync: auth → read local manifest → download media → save locally.
    Never prints token/secret/Authorization/media bytes.
    """
    # ── 1. Read config ─────────────────────────────────────────────
    try:
        cfg = local_config.read_config(args.root)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: Config — {e}", file=sys.stderr)
        sys.exit(1)

    try:
        # ── 2. Secret reader ──────────────────────────────────────
        dev_flag = args.dev_secret_store
        def _read_secret() -> str:
            return secret_store.read_secret(args.root, dev_secret_store=dev_flag)

        secret = _read_secret()
        if not secret:
            print("ERROR: Device secret is empty.", file=sys.stderr)
            sys.exit(1)

        # ── 3. HTTP client ─────────────────────────────────────────
        http_config = HttpClientConfig(
            base_url=cfg["backend_base_url"],
            timeout_sec=cfg.get("request_timeout_sec", 10),
            tls_verify=cfg.get("tls_verify", True),
        )
        http_client = SafeHttpClient(http_config)

        # ── 4. Auth ────────────────────────────────────────────────
        retry_manager = None
        if args.retry_auth:
            policy = BackoffPolicy(max_attempts=args.auth_max_attempts)
            retry_manager = RetryBackoffManager(policy)

        auth = device_auth_client.DeviceAuthClient(
            http_client=http_client,
            config=cfg,
            secret_reader=_read_secret,
        )
        token_state = auth.authenticate(retry_manager=retry_manager)

        # ── 5. Read local manifest ─────────────────────────────────
        manifest = manifest_store.read_current_manifest(args.root)
        items = manifest.get("items", [])
        if not items:
            print("media_sync:           empty_manifest")
            return

        # ── 6. For each item ───────────────────────────────────────
        media_cl = MediaClient(http_client=http_client)
        ensure = media_cache.ensure_media_dirs(args.root)

        items_total = len(items)
        items_cached = 0
        items_downloaded = 0
        items_skipped = 0
        items_missing = 0
        items_failed = 0

        for item in items:
            # Validate item
            filename = item.get("filename", "")
            if not filename:
                items_failed += 1
                continue

            # Verify existing file
            try:
                verify = media_cache.verify_media_file(args.root, item)
            except ValueError:
                items_failed += 1
                continue

            if verify["status"] == "ok":
                # Already valid in cache
                items_cached += 1
                continue

            if verify["status"] == "missing":
                # Download needed
                pass
            elif verify["status"] == "invalid":
                # Corrupted — remove and re-download
                media_cache.quarantine_media_file(args.root, filename, reason="invalid hash")
            else:
                # rejected/error — skip
                items_skipped += 1
                continue

            # Download media
            try:
                manifest_item_id = item.get("manifest_item_id", "")
                if not manifest_item_id:
                    items_failed += 1
                    continue

                content = media_cl.fetch_media(
                    token_state,
                    manifest_item_id,
                    expected_sha256=item.get("sha256", ""),
                    expected_size_bytes=item.get("size_bytes", 0),
                    expected_content_type=item.get("content_type", ""),
                )

                # Write to cache
                result = media_cache.write_media_atomic(args.root, item, content)

                if result["status"] == "written":
                    items_downloaded += 1
                elif result["status"] in ("rejected", "quarantined"):
                    items_failed += 1
                else:
                    items_failed += 1

            except HttpClientError as e:
                if e.status_code == 404:
                    items_missing += 1
                else:
                    items_failed += 1
                # Non-fatal: continue with next item

            except (ValueError, RuntimeError):
                items_failed += 1
                # Non-fatal per item

        # ── 7. Safe output ─────────────────────────────────────────
        cache_complete = (items_cached + items_downloaded) == items_total
        status = "complete" if cache_complete else "incomplete"

        print(f"media_sync:           {status}")
        print(f"items_total:          {items_total}")
        print(f"items_cached:         {items_cached}")
        print(f"items_downloaded:     {items_downloaded}")
        print(f"items_skipped:        {items_skipped}")
        print(f"items_missing:        {items_missing}")
        print(f"items_failed:         {items_failed}")
        print(f"cache_complete:       {str(cache_complete).lower()}")

    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except HttpClientError as e:
        print(f"ERROR: Media sync failed — {e}", file=sys.stderr)
        print(f"retryable:           {e.retryable}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: Media validation — {e}", file=sys.stderr)
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

    # ── Runtime config commands ────────────────────────────────────

    p_rc = sub.add_parser("runtime-config-status", help="Show runtime config health")
    p_rc.add_argument("--root", required=True, help="Root path")
    p_rc.set_defaults(func=cmd_runtime_config_status)

    p_sync = sub.add_parser("sync-runtime-config", help="Full runtime config sync: auth→fetch→save")
    p_sync.add_argument("--root", required=True, help="Root path")
    p_sync.add_argument("--dev-secret-store", action="store_true", default=False,
                        help="Read secret from dev secret store")
    p_sync.add_argument("--retry-auth", action="store_true", default=False,
                        help="Enable retry for auth step")
    p_sync.add_argument("--auth-max-attempts", type=int, default=3,
                        help="Max auth attempts (default: 3)")
    p_sync.set_defaults(func=cmd_sync_runtime_config)

    # ── Heartbeat commands ─────────────────────────────────────────

    p_hb = sub.add_parser("heartbeat-once", help="Send a single heartbeat")
    p_hb.add_argument("--root", required=True, help="Root path")
    p_hb.add_argument("--dev-secret-store", action="store_true", default=False,
                      help="Read secret from dev secret store")
    p_hb.add_argument("--status", type=str, default="ok",
                      help="Heartbeat status: ok/warning/error")
    p_hb.add_argument("--message", type=str, default=None)
    p_hb.add_argument("--app-version", type=str, default=None)
    p_hb.add_argument("--os-version", type=str, default=None)
    p_hb.add_argument("--storage-free-mb", type=int, default=None)
    p_hb.add_argument("--cache-items-count", type=int, default=None)
    p_hb.add_argument("--current-manifest-hash", type=str, default=None)
    p_hb.add_argument("--retry-auth", action="store_true", default=False,
                      help="Enable retry for auth step")
    p_hb.add_argument("--auth-max-attempts", type=int, default=3,
                      help="Max auth attempts (default: 3)")
    p_hb.add_argument("--retry-heartbeat", action="store_true", default=False,
                      help="Enable retry for heartbeat step")
    p_hb.add_argument("--heartbeat-max-attempts", type=int, default=3,
                      help="Max heartbeat attempts when --retry-heartbeat (default: 3)")
    p_hb.set_defaults(func=cmd_heartbeat_once)

    # ── Manifest commands ───────────────────────────────────────────

    p_ms = sub.add_parser("manifest-status", help="Show local manifest health")
    p_ms.add_argument("--root", required=True, help="Root path")
    p_ms.set_defaults(func=cmd_manifest_status)

    p_mcs = sub.add_parser("media-cache-status", help="Show local media cache health")
    p_mcs.add_argument("--root", required=True, help="Root path")
    p_mcs.set_defaults(func=cmd_media_cache_status)

    p_smf = sub.add_parser("sync-manifest", help="Sync manifest: auth→fetch→save")
    p_smf.add_argument("--root", required=True, help="Root path")
    p_smf.add_argument("--dev-secret-store", action="store_true", default=False,
                       help="Read secret from dev secret store")
    p_smf.add_argument("--retry-auth", action="store_true", default=False,
                       help="Enable retry for auth step")
    p_smf.add_argument("--auth-max-attempts", type=int, default=3,
                       help="Max auth attempts (default: 3)")
    p_smf.set_defaults(func=cmd_sync_manifest)

    p_smd = sub.add_parser("sync-media", help="Sync media: auth→read manifest→download media→save")
    p_smd.add_argument("--root", required=True, help="Root path")
    p_smd.add_argument("--dev-secret-store", action="store_true", default=False,
                       help="Read secret from dev secret store")
    p_smd.add_argument("--retry-auth", action="store_true", default=False,
                       help="Enable retry for auth step")
    p_smd.add_argument("--auth-max-attempts", type=int, default=3,
                       help="Max auth attempts (default: 3)")
    p_smd.set_defaults(func=cmd_sync_media)

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
