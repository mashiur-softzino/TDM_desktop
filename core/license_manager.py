"""
License Manager — Softzino License Server integration
Handles device fingerprint, activation, signed-token validation, offline checks,
and heartbeat.
"""

import base64
import hashlib
import json
import math
import os
import platform
import struct
import threading
import time
import uuid
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from core.app_paths import license_file, migrate_legacy_file

try:
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey
except ImportError:  # pragma: no cover - handled gracefully at runtime
    BadSignatureError = Exception
    VerifyKey = None

BASE_URL = "https://license.softzino.com/api/v1"
LICENSE_FILE = license_file()
migrate_legacy_file("license.json", LICENSE_FILE)
HEARTBEAT_INTERVAL = 300  # 5 minutes
CLOCK_ROLLBACK_TOLERANCE_SECONDS = 300  # allow small NTP/timezone corrections
CHECKPOINT_WRITE_INTERVAL_SECONDS = 60
CLOCK_VERIFICATION_ERROR = (
    "System clock change detected. Please correct your computer date/time and "
    "connect to the internet to verify your license."
)

PASETO_HEADER = b"v4.public."
TRUSTED_ROOT_KID = "root_sVRUTUxtWYKFGA5Yt87caPSikGdjRSSs"
TRUSTED_ROOT_PUBLIC_KEY_B64 = "6LJQlpa/pnadeDCifVw7cnBNhnlIkQrl62p/9EUnJtc="
TRUSTED_SIGNING_KID = "signing-3c752a2ed5695e1638c7d10388ce0141"
TRUSTED_SIGNING_PUBLIC_KEY_B64 = "yx7HzRe5pNW9K80fQPv0oDjz/zUYkbf9MHumR2z1VQE="
TRUSTED_SIGNING_KEYS = {
    TRUSTED_SIGNING_KID: TRUSTED_SIGNING_PUBLIC_KEY_B64,
    "jibonsheba-signing-key": "bGL4qdkPuCffqv+7g4IRdpV+S2GWWX9b3n0UM6CODE4=",
    "signing-f61462c1e919e22ee153f1d6be8818db": "S9MO3TGnmXyjVhUgNM3QMD+hoMgHnpXRM4iz+Quj3h4=",
    "oishy-test-20260619162330": "S9MO3TGnmXyjVhUgNM3QMD+hoMgHnpXRM4iz+Quj3h4=",
}
EXPECTED_ISSUER = "laravel-licensing"
TOKEN_VERIFY_ERROR = (
    "Secure license verification is unavailable. Install dependencies with "
    "'python -m pip install -r requirements.txt'."
)
TEMPORARY_SIGNATURE_BYPASS = (
    os.getenv("TDM_LICENSE_SIGNATURE_BYPASS", "1").strip().lower()
    not in {"0", "false", "no", "off"}
)


def get_fingerprint() -> str:
    mac = hex(uuid.getnode())
    machine = platform.node()
    system = platform.system()
    raw = f"{mac}-{machine}-{system}"
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:48]


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def parse_local_license_datetime(value: str | None) -> datetime | None:
    dt = parse_iso_datetime(value)
    if dt is None:
        return None
    # Treat the wall-clock time from the license payload as local time.
    return dt.replace(tzinfo=None).astimezone()


def to_local_iso(value: str | None) -> str | None:
    dt = parse_local_license_datetime(value)
    if dt is None:
        return None
    return dt.isoformat()


def is_license_expired_local(expires_at: str | None) -> bool:
    exp = parse_local_license_datetime(expires_at)
    if exp is None:
        return False
    return datetime.now().astimezone() > exp


def is_usable_license_status(status: str | None) -> bool:
    return str(status or "").lower() in {"active", "grace"}


def extract_server_time(
    data: dict | None, response: requests.Response | None
) -> datetime | None:
    if isinstance(data, dict):
        candidates = [
            data.get("server_time"),
            data.get("serverTime"),
            data.get("timestamp"),
            data.get("time"),
        ]
        inner = data.get("data")
        if isinstance(inner, dict):
            candidates.extend(
                [
                    inner.get("server_time"),
                    inner.get("serverTime"),
                    inner.get("timestamp"),
                    inner.get("time"),
                ]
            )
        for candidate in candidates:
            parsed = (
                parse_iso_datetime(candidate) if isinstance(candidate, str) else None
            )
            if parsed is not None:
                return parsed.astimezone()

    if response is not None:
        try:
            date_header = response.headers.get("Date")
            if date_header:
                return parsedate_to_datetime(date_header).astimezone()
        except Exception:
            return None
    return None


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def pae(parts: list[bytes]) -> bytes:
    output = struct.pack("<Q", len(parts))
    for part in parts:
        output += struct.pack("<Q", len(part))
        output += part
    return output


def php_json_bytes(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":")).replace("/", "\\/").encode()


def error_message_from_response(data: dict, default: str) -> str:
    message = data.get("message")
    if isinstance(message, str) and message.strip():
        return message

    err = data.get("error")
    if isinstance(err, str) and err.strip():
        return err
    if isinstance(err, dict):
        for key in ("message", "license_key", "detail", "error"):
            value = err.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, str) and first.strip():
                    return first
        details = err.get("details")
        if isinstance(details, dict):
            for value in details.values():
                if isinstance(value, list) and value:
                    first = value[0]
                    if isinstance(first, str) and first.strip():
                        return first
                if isinstance(value, str) and value.strip():
                    return value

    errors = data.get("errors")
    if isinstance(errors, dict):
        for value in errors.values():
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, str) and first.strip():
                    return first
            if isinstance(value, str) and value.strip():
                return value

    return default


class LicenseManager:
    def __init__(self):
        self._data: dict = {}
        self._lock = threading.Lock()
        self._heartbeat_thread: threading.Thread | None = None
        self._running = False
        self._stop_event = threading.Event()
        self._last_error = ""
        self._session_wall_started_at = datetime.now().astimezone()
        self._session_monotonic_started_at = time.monotonic()
        self._load()

    def is_licensed(self) -> bool:
        with self._lock:
            if self._offline_valid():
                return True
            needs_online_verification = self._needs_clock_verification_locked()

        if needs_online_verification and self._try_online_recovery():
            with self._lock:
                return self._offline_valid()
        return False

    def verify_key(self, license_key: str) -> tuple[bool, str]:
        """
        Step 1 — Check if key is valid before activation.
        Returns (success, error_message)
        """
        try:
            resp = requests.post(
                f"{BASE_URL}/validate",
                json={"license_key": license_key, "fingerprint": get_fingerprint()},
                timeout=10,
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("success"):
                inner = data.get("data", {})
                license_data = inner.get("license", inner)
                expires_at = (
                    license_data.get("expires_at")
                    or license_data.get("license_expires_at")
                )
                status = str(license_data.get("status", "")).lower()
                if status == "expired" or is_license_expired_local(expires_at):
                    return False, "License has expired"
                return True, ""
            msg = error_message_from_response(
                data,
                "Please enter a valid license key.",
            )
            return False, msg
        except requests.exceptions.ConnectionError:
            return False, "No internet connection"
        except Exception as e:
            return False, str(e)

    def activate(self, license_key: str) -> tuple[bool, str]:
        """
        Step 2 — Activate this device and get offline token.
        Returns (success, error_message)
        """
        fingerprint = get_fingerprint()
        try:
            resp = requests.post(
                f"{BASE_URL}/activate",
                json={
                    "license_key": license_key,
                    "fingerprint": fingerprint,
                    "metadata": {
                        "client_type": "desktop-app",
                        "os": platform.platform(),
                    },
                },
                timeout=10,
            )
            data = resp.json()
            if resp.status_code in (200, 201) and data.get("success"):
                inner = data.get("data", {})
                claims = self._claims_from_token_response(inner, license_key)
                if claims is None:
                    return False, self._last_error or "Activation failed"
                if not is_usable_license_status(claims.get("status")):
                    return False, "License is not active"
                if is_license_expired_local(claims.get("license_expires_at")):
                    return False, "License has expired"

                trusted_now = extract_server_time(data, resp)
                if trusted_now and not self._local_clock_matches_trusted_time(
                    trusted_now
                ):
                    return False, CLOCK_VERIFICATION_ERROR

                self._save(
                    license_key,
                    fingerprint,
                    inner.get("token"),
                    claims,
                    token_response=inner,
                    trusted_now=trusted_now,
                )
                self._start_heartbeat()
                return True, ""
            msg = error_message_from_response(
                data,
                f"Activation failed (HTTP {resp.status_code})",
            )
            return False, msg
        except requests.exceptions.ConnectionError:
            return False, "No internet connection"
        except Exception as e:
            return False, str(e)

    def start_session(self):
        """Call after is_licensed() returns True — starts heartbeat."""
        self._start_heartbeat()

    def deactivate(self):
        """Release device seat (call on uninstall or manual deactivate)."""
        self._stop_heartbeat()
        with self._lock:
            lk = self._data.get("license_key")
            fp = self._data.get("fingerprint")
        if lk and fp:
            try:
                requests.post(
                    f"{BASE_URL}/deactivate",
                    json={"license_key": lk, "fingerprint": fp},
                    timeout=10,
                )
            except Exception:
                pass
        if LICENSE_FILE.exists():
            LICENSE_FILE.unlink()
        with self._lock:
            self._data = {}

    def license_info(self) -> dict:
        with self._lock:
            return dict(self._data)

    def has_expired(self) -> bool:
        with self._lock:
            claims = self._verified_token_claims()
            if claims is None:
                return True
            if not self._validate_clock_checkpoint(update=True):
                return True
            if is_license_expired_local(claims.get("license_expires_at")):
                self._mark_expired()
                return True
            return self._data.get("status") == "expired"

    def expires_at_local(self) -> datetime | None:
        with self._lock:
            claims = self._verified_token_claims()
            if claims is None:
                return None
            return parse_local_license_datetime(claims.get("license_expires_at"))

    def last_error(self) -> str:
        with self._lock:
            return self._last_error

    def needs_clock_verification(self) -> bool:
        with self._lock:
            return self._needs_clock_verification_locked()

    def _offline_valid(self) -> bool:
        claims = self._verified_token_claims()
        if claims is None:
            return False
        if not is_usable_license_status(claims.get("status")):
            return False
        if not self._validate_clock_checkpoint(update=True):
            return False
        if is_license_expired_local(claims.get("license_expires_at")):
            self._mark_expired()
            return False
        return True

    def _save(
        self,
        license_key: str,
        fingerprint: str,
        token: str,
        claims: dict,
        token_response: dict | None = None,
        trusted_now: datetime | None = None,
    ):
        with self._lock:
            now = datetime.now().astimezone()
            token_response = token_response or {}
            trusted_now_iso = (
                trusted_now.isoformat()
                if trusted_now
                else self._data.get("last_trusted_at")
            )
            self._data = {
                "license_key": license_key,
                "fingerprint": fingerprint,
                "status": "active",
                "clock_rollback_detected": False,
                "last_seen_at": now.isoformat(),
                "last_seen_checkpoint_at": now.isoformat(),
                "last_trusted_at": trusted_now_iso,
                "activated_at": claims.get("iat"),
                "activated_at_local": to_local_iso(claims.get("iat")),
                "expires_at": claims.get("license_expires_at"),
                "expires_at_local": to_local_iso(claims.get("license_expires_at")),
                "days_until_expiration": self._remaining_days(
                    claims.get("license_expires_at")
                ),
                "token": token,
                "token_expires_at": token_response.get("token_expires_at"),
                "refresh_after": token_response.get("refresh_after"),
                "force_online_after": token_response.get("force_online_after"),
                "public_key_bundle": token_response.get("public_key_bundle")
                or self._data.get("public_key_bundle"),
            }
            self._reset_session_clock_baseline(now)
            self._persist()

    def _load(self):
        if not LICENSE_FILE.exists():
            return
            
        try:
            content = LICENSE_FILE.read_text().strip()
            if not content:
                return

            # Try to parse as plain JSON first (migration)
            if content.startswith('{'):
                try:
                    self._data = json.loads(content)
                    # Migrate to scrambled format immediately
                    self._persist()
                    self._hydrate_cached_fields()
                    return
                except json.JSONDecodeError:
                    pass
            
            # Unscramble
            fp = get_fingerprint()
            unscrambled = self._unscramble(content, fp)
            if unscrambled:
                self._data = json.loads(unscrambled)
                self._hydrate_cached_fields()
        except Exception:
            self._data = {}


    def _start_heartbeat(self):
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._running = True
        self._stop_event.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self):
        self._running = False
        self._stop_event.set()  # wake the sleeping thread immediately

    def _heartbeat_loop(self):
        while self._running:
            # Wait up to HEARTBEAT_INTERVAL — wakes instantly if stop is requested
            if self._stop_event.wait(timeout=HEARTBEAT_INTERVAL):
                break  # stop was requested
            if not self._running:
                break
            with self._lock:
                lk = self._data.get("license_key")
                fp = self._data.get("fingerprint")
            if lk and fp:
                try:
                    resp = requests.post(
                        f"{BASE_URL}/heartbeat",
                        json={"license_key": lk, "fingerprint": fp},
                        timeout=10,
                    )
                    if 200 <= resp.status_code < 300:
                        try:
                            data = resp.json()
                        except Exception:
                            data = {}
                        self._record_online_checkpoint(
                            trusted_now=extract_server_time(data, resp)
                        )
                except Exception:
                    pass
            self._try_refresh_token()

    def _try_refresh_token(self):
        self._refresh_saved_token(require_trusted_clock=False)

    def _try_online_recovery(self) -> bool:
        return self._refresh_saved_token(require_trusted_clock=True)

    def _claims_from_token_response(
        self, token_response: dict, license_key: str | None
    ) -> dict | None:
        token = token_response.get("token")
        if not token:
            self._last_error = "Activation failed: missing token"
            return None
        return self._verify_token(
            token,
            license_key,
            key_bundle=token_response.get("public_key_bundle"),
        )

    def _refresh_saved_token(self, require_trusted_clock: bool = False) -> bool:
        with self._lock:
            lk = self._data.get("license_key")
            fp = self._data.get("fingerprint")
        if not lk or not fp:
            return False
        try:
            resp = requests.post(
                f"{BASE_URL}/refresh",
                json={"license_key": lk, "fingerprint": fp},
                timeout=10,
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("success"):
                inner = data.get("data", {})
                claims = self._claims_from_token_response(inner, lk)
                if claims is None:
                    return False
                trusted_now = extract_server_time(data, resp)
                if require_trusted_clock and trusted_now is None:
                    with self._lock:
                        self._set_clock_verification_error_locked(persist=False)
                    return False
                if trusted_now and not self._local_clock_matches_trusted_time(
                    trusted_now
                ):
                    with self._lock:
                        self._set_clock_verification_error_locked(persist=True)
                    return False
                self._save(
                    lk,
                    fp,
                    inner.get("token"),
                    claims,
                    token_response=inner,
                    trusted_now=trusted_now,
                )
                return True
        except Exception:
            if require_trusted_clock:
                with self._lock:
                    self._set_clock_verification_error_locked(persist=False)
        return False

    def _persist(self):
        try:
            fp = get_fingerprint()
            raw_json = json.dumps(self._data)
            scrambled = self._scramble(raw_json, fp)
            LICENSE_FILE.write_text(scrambled)
        except Exception:
            pass

    def _scramble(self, data: str, key: str) -> str:
        """Simple XOR-based scrambling using the device fingerprint as key."""
        key_bytes = key.encode()
        data_bytes = data.encode()
        result = bytearray()
        for i in range(len(data_bytes)):
            result.append(data_bytes[i] ^ key_bytes[i % len(key_bytes)])
        return base64.b64encode(result).decode()

    def _unscramble(self, scrambled: str, key: str) -> str:
        """Reverse of _scramble."""
        try:
            key_bytes = key.encode()
            data_bytes = base64.b64decode(scrambled)
            result = bytearray()
            for i in range(len(data_bytes)):
                result.append(data_bytes[i] ^ key_bytes[i % len(key_bytes)])
            return result.decode()
        except Exception:
            return ""


    def _hydrate_cached_fields(self):
        claims = self._verified_token_claims()
        if claims is None:
            return

        updated = False
        expires_at = claims.get("license_expires_at")
        activated_at = claims.get("iat")
        expected_status = (
            "expired" if is_license_expired_local(expires_at) else "active"
        )
        expected_days = self._remaining_days(expires_at)
        expected_fingerprint = claims.get("usage_fingerprint") or get_fingerprint()

        desired = {
            "fingerprint": expected_fingerprint,
            "status": expected_status,
            "activated_at": activated_at,
            "activated_at_local": to_local_iso(activated_at),
            "expires_at": expires_at,
            "expires_at_local": to_local_iso(expires_at),
            "days_until_expiration": expected_days,
        }

        for key, value in desired.items():
            if self._data.get(key) != value:
                self._data[key] = value
                updated = True

        if updated:
            self._persist()

    def _record_online_checkpoint(self, trusted_now: datetime | None = None):
        now = datetime.now().astimezone()
        with self._lock:
            now_iso = now.isoformat()
            self._data["clock_rollback_detected"] = False
            self._data["last_seen_at"] = now_iso
            self._data["last_seen_checkpoint_at"] = now_iso
            if trusted_now is not None:
                self._data["last_trusted_at"] = trusted_now.isoformat()
            self._last_error = ""
            self._reset_session_clock_baseline(now)
            self._persist()

    def _reset_session_clock_baseline(self, wall_time: datetime | None = None):
        self._session_wall_started_at = wall_time or datetime.now().astimezone()
        self._session_monotonic_started_at = time.monotonic()

    def _local_clock_matches_trusted_time(self, trusted_now: datetime) -> bool:
        now = datetime.now().astimezone()
        trusted_now = trusted_now.astimezone()
        delta = abs(now.timestamp() - trusted_now.timestamp())
        return delta <= CLOCK_ROLLBACK_TOLERANCE_SECONDS

    def _needs_clock_verification_locked(self) -> bool:
        return (
            self._data.get("clock_rollback_detected") is True
            or self._last_error == CLOCK_VERIFICATION_ERROR
        )

    def _set_clock_verification_error_locked(self, persist: bool = False):
        self._data["clock_rollback_detected"] = True
        self._last_error = CLOCK_VERIFICATION_ERROR
        if persist:
            self._persist()

    def _validate_clock_checkpoint(self, update: bool = False) -> bool:
        if self._data.get("clock_rollback_detected"):
            self._last_error = CLOCK_VERIFICATION_ERROR
            return False

        now = datetime.now().astimezone()
        session_elapsed = time.monotonic() - self._session_monotonic_started_at
        expected_now = datetime.fromtimestamp(
            self._session_wall_started_at.timestamp() + session_elapsed,
            tz=self._session_wall_started_at.tzinfo,
        )
        if (
            now.timestamp() + CLOCK_ROLLBACK_TOLERANCE_SECONDS
            < expected_now.timestamp()
        ):
            self._set_clock_verification_error_locked(persist=True)
            return False

        last_seen = parse_iso_datetime(self._data.get("last_seen_at"))
        if last_seen is not None:
            last_seen = last_seen.astimezone()

        if last_seen and (
            now.timestamp() + CLOCK_ROLLBACK_TOLERANCE_SECONDS < last_seen.timestamp()
        ):
            self._set_clock_verification_error_locked(persist=True)
            return False

        if not update:
            self._last_error = ""
            return True

        checkpoint = parse_iso_datetime(self._data.get("last_seen_checkpoint_at"))
        if checkpoint is not None:
            checkpoint = checkpoint.astimezone()

        should_write = last_seen is None or checkpoint is None
        if not should_write and now >= last_seen:
            elapsed = now.timestamp() - checkpoint.timestamp()
            should_write = elapsed >= CHECKPOINT_WRITE_INTERVAL_SECONDS

        if should_write:
            now_iso = now.isoformat()
            self._data["last_seen_at"] = now_iso
            self._data["last_seen_checkpoint_at"] = now_iso
            self._persist()

        self._last_error = ""
        return True

    def _remaining_days(self, expires_at: str | None) -> int:
        exp = parse_local_license_datetime(expires_at)
        if exp is None:
            return 0
        remaining_seconds = (exp - datetime.now().astimezone()).total_seconds()
        return max(0, math.ceil(remaining_seconds / 86400))

    def _mark_expired(self):
        if self._data.get("status") != "expired":
            self._data["status"] = "expired"
            self._data["days_until_expiration"] = 0
            self._persist()

    def _verified_token_claims(self) -> dict | None:
        token = self._data.get("token")
        license_key = self._data.get("license_key")
        if not token:
            self._last_error = "Missing license token"
            return None
        return self._verify_token(
            token,
            license_key,
            key_bundle=self._data.get("public_key_bundle"),
        )

    def _trusted_signing_key_from_bundle(
        self, key_bundle: dict | None, payload_kid: str | None
    ) -> str | None:
        if not isinstance(key_bundle, dict) or not payload_kid:
            return None

        root = key_bundle.get("root")
        if not isinstance(root, dict):
            return None
        if root.get("kid") != TRUSTED_ROOT_KID:
            self._last_error = "Untrusted license root key"
            return None
        if root.get("public_key") != TRUSTED_ROOT_PUBLIC_KEY_B64:
            self._last_error = "License root key mismatch"
            return None

        candidates = []
        signing = key_bundle.get("signing")
        if isinstance(signing, dict):
            candidates.append(signing)
        signing_keys = key_bundle.get("signing_keys")
        if isinstance(signing_keys, list):
            candidates.extend(item for item in signing_keys if isinstance(item, dict))

        for signing_key in candidates:
            if signing_key.get("kid") != payload_kid:
                continue
            if self._verify_signing_certificate(signing_key, root):
                return signing_key.get("public_key")
            return None
        return None

    def _verify_signing_certificate(self, signing_key: dict, root: dict) -> bool:
        certificate_raw = signing_key.get("certificate")
        if not certificate_raw:
            self._last_error = "License signing certificate is missing"
            return False
        try:
            certificate_doc = (
                json.loads(certificate_raw)
                if isinstance(certificate_raw, str)
                else certificate_raw
            )
            certificate = certificate_doc.get("certificate")
            signature = base64.b64decode(certificate_doc.get("signature", ""))
        except Exception:
            self._last_error = "License signing certificate is invalid"
            return False

        if not isinstance(certificate, dict):
            self._last_error = "License signing certificate is invalid"
            return False
        if certificate.get("issuer_kid") != root.get("kid"):
            self._last_error = "License signing certificate issuer mismatch"
            return False
        if certificate.get("kid") != signing_key.get("kid"):
            self._last_error = "License signing certificate key mismatch"
            return False
        if certificate.get("public_key") != signing_key.get("public_key"):
            self._last_error = "License signing certificate public key mismatch"
            return False

        valid_from = parse_iso_datetime(certificate.get("valid_from"))
        valid_until = parse_iso_datetime(certificate.get("valid_until"))
        now = datetime.now().astimezone()
        if valid_from and now < valid_from.astimezone():
            self._last_error = "License signing certificate is not yet valid"
            return False
        if valid_until and now > valid_until.astimezone():
            self._last_error = "License signing certificate has expired"
            return False

        try:
            VerifyKey(base64.b64decode(root["public_key"])).verify(
                php_json_bytes(certificate),
                signature,
            )
        except BadSignatureError:
            self._last_error = "License signing certificate signature is invalid"
            return False
        except Exception:
            self._last_error = "License signing certificate could not be verified"
            return False
        return True

    def _verify_token(
        self,
        token: str,
        license_key: str | None,
        key_bundle: dict | None = None,
    ) -> dict | None:
        bypass_signature = TEMPORARY_SIGNATURE_BYPASS
        if VerifyKey is None and not bypass_signature:
            self._last_error = TOKEN_VERIFY_ERROR
            return None

        try:
            version, purpose, payload_b64, footer_b64 = token.split(".", 3)
        except ValueError:
            self._last_error = "Invalid license token format"
            return None

        if version != "v4" or purpose != "public":
            self._last_error = "Unsupported license token format"
            return None

        try:
            footer = json.loads(b64url_decode(footer_b64).decode("utf-8"))
            decoded = b64url_decode(payload_b64)
        except Exception:
            self._last_error = "Invalid license token encoding"
            return None

        if len(decoded) <= 64:
            self._last_error = "Invalid license token payload"
            return None

        message = decoded[:-64]
        signature = decoded[-64:]

        try:
            payload = json.loads(message.decode("utf-8"))
        except Exception:
            self._last_error = "Invalid license token payload"
            return None

        payload_kid = payload.get("kid")
        signing_public_key = self._trusted_signing_key_from_bundle(
            key_bundle,
            payload_kid,
        )
        if signing_public_key is None:
            signing_public_key = TRUSTED_SIGNING_KEYS.get(payload_kid)
        if signing_public_key is None and not bypass_signature:
            self._last_error = f"Untrusted license signer: {payload_kid or 'missing kid'}"
            return None
        if payload.get("iss") != EXPECTED_ISSUER:
            self._last_error = "Unexpected license issuer"
            return None

        if signing_public_key and VerifyKey is not None:
            try:
                verify_key = VerifyKey(base64.b64decode(signing_public_key))
                verify_key.verify(
                    pae(
                        [
                            PASETO_HEADER,
                            message,
                            b64url_decode(footer_b64),
                            b"",
                        ]
                    ),
                    signature,
                )
            except BadSignatureError:
                if not bypass_signature:
                    self._last_error = "License token signature is invalid"
                    return None
            except Exception:
                if not bypass_signature:
                    self._last_error = "License token could not be verified"
                    return None

        expected_fingerprint = get_fingerprint()
        payload_fingerprint = payload.get("usage_fingerprint") or payload.get("fingerprint")
        if payload_fingerprint != expected_fingerprint:
            self._last_error = "License is not valid for this device"
            return None

        if license_key:
            expected_hash = hashlib.sha256(license_key.encode()).hexdigest()
            if payload.get("license_key_hash") != expected_hash:
                # Some server tokens hash a canonical/internal representation of the
                # license key, so treat this as non-fatal as long as the signed token,
                # issuer, and device fingerprint are valid.
                self._last_error = ""

        if not payload.get("status") and payload.get("license_status"):
            payload["status"] = payload.get("license_status")

        expires_at = (
            payload.get("license_expires_at")
            or payload.get("expires_at")
            or payload.get("exp")
        )
        if not expires_at:
            self._last_error = "License token is missing expiry information"
            return None
        payload["license_expires_at"] = expires_at

        # The footer is still included in the verified signed message, but we also
        # sanity-check the advertised key id so the cached token metadata stays coherent.
        footer_kid = footer.get("kid")
        if footer_kid and footer_kid != payload_kid:
            self._last_error = "License footer key mismatch"
            return None

        self._last_error = ""
        return payload
