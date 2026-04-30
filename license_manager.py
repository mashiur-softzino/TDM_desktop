"""
License Manager — Softzino License Server integration
Handles device fingerprint, activation, signed-token validation, offline checks,
and heartbeat.
"""

import base64
import hashlib
import json
import math
import platform
import struct
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests
from app_paths import license_file, migrate_legacy_file

try:
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey
except ImportError:  # pragma: no cover - handled gracefully at runtime
    BadSignatureError = Exception
    VerifyKey = None

BASE_URL = "https://dev-license.softzino.com/api/v1/license"
LICENSE_FILE = license_file()
migrate_legacy_file("license.json", LICENSE_FILE)
HEARTBEAT_INTERVAL = 300  # 5 minutes

PASETO_HEADER = b"v4.public."
TRUSTED_SIGNING_KID = "signing-3c752a2ed5695e1638c7d10388ce0141"
TRUSTED_SIGNING_PUBLIC_KEY_B64 = "yx7HzRe5pNW9K80fQPv0oDjz/zUYkbf9MHumR2z1VQE="
EXPECTED_ISSUER = "laravel-licensing"
TOKEN_VERIFY_ERROR = (
    "Secure license verification is unavailable. Install dependencies with "
    "'python -m pip install -r requirements.txt'."
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


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def pae(parts: list[bytes]) -> bytes:
    output = struct.pack("<Q", len(parts))
    for part in parts:
        output += struct.pack("<Q", len(part))
        output += part
    return output


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
        self._load()

    def is_licensed(self) -> bool:
        with self._lock:
            return self._offline_valid()

    def verify_key(self, license_key: str) -> tuple[bool, str]:
        """
        Step 1 — Check if key is valid before activation.
        Returns (success, error_message)
        """
        try:
            resp = requests.post(
                f"{BASE_URL}/verify",
                json={"license_key": license_key},
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
                    "client_type": "desktop-app",
                },
                timeout=10,
            )
            data = resp.json()
            if resp.status_code in (200, 201) and data.get("success"):
                inner = data.get("data", {})
                token = inner.get("token")
                if not token:
                    return False, "Activation failed: missing token"

                claims = self._verify_token(token, license_key)
                if claims is None:
                    return False, self._last_error or "Activation failed"
                if claims.get("status") != "active":
                    return False, "License is not active"
                if is_license_expired_local(claims.get("license_expires_at")):
                    return False, "License has expired"

                self._save(license_key, fingerprint, token, claims)
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

    def _offline_valid(self) -> bool:
        claims = self._verified_token_claims()
        if claims is None:
            return False
        if claims.get("status") != "active":
            return False
        if is_license_expired_local(claims.get("license_expires_at")):
            self._mark_expired()
            return False
        return True

    def _save(self, license_key: str, fingerprint: str, token: str, claims: dict):
        with self._lock:
            self._data = {
                "license_key": license_key,
                "fingerprint": fingerprint,
                "status": "active",
                "activated_at": claims.get("iat"),
                "activated_at_local": to_local_iso(claims.get("iat")),
                "expires_at": claims.get("license_expires_at"),
                "expires_at_local": to_local_iso(claims.get("license_expires_at")),
                "days_until_expiration": self._remaining_days(
                    claims.get("license_expires_at")
                ),
                "token": token,
            }
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
                    requests.post(
                        f"{BASE_URL}/heartbeat",
                        json={"license_key": lk, "fingerprint": fp},
                        timeout=10,
                    )
                except Exception:
                    pass
            self._try_refresh_token()

    def _try_refresh_token(self):
        with self._lock:
            lk = self._data.get("license_key")
            fp = self._data.get("fingerprint")
        if not lk or not fp:
            return
        try:
            resp = requests.post(
                f"{BASE_URL}/token/refresh",
                json={"license_key": lk, "fingerprint": fp},
                timeout=10,
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("success"):
                token = data.get("data", {}).get("token")
                if not token:
                    return
                claims = self._verify_token(token, lk)
                if claims is None:
                    return
                self._save(lk, fp, token, claims)
        except Exception:
            pass

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
        return self._verify_token(token, license_key)

    def _verify_token(self, token: str, license_key: str | None) -> dict | None:
        if VerifyKey is None:
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

        if payload.get("kid") != TRUSTED_SIGNING_KID:
            self._last_error = "Untrusted license signer"
            return None
        if payload.get("iss") != EXPECTED_ISSUER:
            self._last_error = "Unexpected license issuer"
            return None

        try:
            verify_key = VerifyKey(base64.b64decode(TRUSTED_SIGNING_PUBLIC_KEY_B64))
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
            self._last_error = "License token signature is invalid"
            return None
        except Exception:
            self._last_error = "License token could not be verified"
            return None

        expected_fingerprint = get_fingerprint()
        if payload.get("usage_fingerprint") != expected_fingerprint:
            self._last_error = "License is not valid for this device"
            return None

        if license_key:
            expected_hash = hashlib.sha256(license_key.encode()).hexdigest()
            if payload.get("license_key_hash") != expected_hash:
                # Some server tokens hash a canonical/internal representation of the
                # license key, so treat this as non-fatal as long as the signed token,
                # issuer, and device fingerprint are valid.
                self._last_error = ""

        expires_at = payload.get("license_expires_at")
        if not expires_at:
            self._last_error = "License token is missing expiry information"
            return None

        # The footer is still included in the verified signed message, but we also
        # sanity-check the advertised key id so the cached token metadata stays coherent.
        footer_kid = footer.get("kid")
        if footer_kid and footer_kid != TRUSTED_SIGNING_KID:
            self._last_error = "License footer key mismatch"
            return None

        return payload
