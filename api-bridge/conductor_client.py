"""
D-Cloud Holochain Conductor WebSocket Client
=============================================
Implements the Holochain conductor App + Admin WebSocket protocol for Python.

Holochain conductor wire protocol (0.3.6):
  - All messages are msgpack-encoded
  - Outer frame: {"id": <uint64>, "type": "request",  "data": <bytes>}
                 {"id": <uint64>, "type": "response", "data": <bytes>}
  - The "data" field is itself a msgpack-encoded blob (nested encoding).
  - AppRequest CallZome payload (inside "data") MUST be a *signed* ZomeCall:
      {"type": "call_zome", "data": {
          "cell_id": [<dna_hash:bytes>, <agent_pubkey:bytes>],
          "zome_name": str,
          "fn_name": str,
          "payload": <ExternIO bytes (msgpack of input)>,
          "cap_secret": <64-byte cap secret>,
          "provenance": <agent_pubkey:bytes>,
          "nonce": <32 random bytes>,
          "expires_at": <int microseconds>,
          "signature": <64-byte Ed25519 sig of blake3(msgpack(ZomeCallUnsigned))>
      }}

Holochain 0.3.x requires Ed25519-signed ZomeCalls. On connect(), this client:
  1. Generates a temporary Ed25519 keypair (nacl.signing.SigningKey)
  2. Constructs an "unrestricted" CapGrant via Admin API grant_zome_call_capability
  3. Signs each ZomeCall with blake3( msgpack(ZomeCallUnsigned) ) → Ed25519 signature

Wire framing verified against @holochain/client 0.17.x source code.

Locked versions: websockets==12.0 | msgpack==1.0.8 | PyNaCl | blake3
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import msgpack

# websockets 12.0 — use the top-level asyncio-native connect(), NOT the legacy shim.
import websockets
from websockets import WebSocketClientProtocol

# ZomeCall signing: PyNaCl for Ed25519, blake3 for hashing the call struct.
try:
    import nacl.signing
    import nacl.encoding
    _HAS_NACL = True
except ImportError:
    _HAS_NACL = False
    logger_bootstrap = logging.getLogger("d-cloud.conductor")
    logger_bootstrap.warning("PyNaCl not installed — ZomeCall signing disabled (will fail on 0.3.x conductors)")

try:
    import blake3 as blake3_lib
    _HAS_BLAKE3 = True
except ImportError:
    _HAS_BLAKE3 = False

# blake2b-256 is available in the stdlib hashlib (no extra dependency)
import hashlib

logger = logging.getLogger("d-cloud.conductor")


# ─────────────────────────────────────────────────────────────────────────────
# ZomeCall signing helpers
# ─────────────────────────────────────────────────────────────────────────────

_NONCE_BYTES = 32
_CAP_SECRET_BYTES = 64
_NONCE_EXPIRY_MICROS = 5 * 60 * 1_000_000  # 5 minutes


def _new_signing_key():
    """Generate a new Ed25519 signing key pair via PyNaCl."""
    if not _HAS_NACL:
        return None
    return nacl.signing.SigningKey.generate()


def _signing_key_to_agent_pubkey(sk) -> bytes:
    """
    Convert a PyNaCl SigningKey to a Holochain AgentPubKey (39-byte format).
    Holochain AgentPubKey = [0x84, 0x20, 0x24] + 32-byte ED25519 public key + 4-byte DHT location.
    We set the location bytes to 0x00 for locally-issued ephemeral keys.
    """
    pub_bytes = bytes(sk.verify_key)  # 32 bytes
    return bytes([0x84, 0x20, 0x24]) + pub_bytes + bytes(4)


def _hash_zome_call(call_unsigned: dict) -> bytes:
    """
    Hash a ZomeCallUnsigned dict for signing.
    Matches holochain_zome_types ZomeCallUnsigned::data_to_sign():
      blake2b_256( holochain_serialized_bytes::encode(self) )

    IMPORTANT: The field order in call_unsigned MUST match the Rust struct definition:
      provenance, cell_id, zome_name, fn_name, cap_secret, payload, nonce, expires_at
    """
    encoded = msgpack.packb(call_unsigned, use_bin_type=True)
    # holochain uses blake2b with 256-bit (32-byte) digest, NOT blake3
    hasher = hashlib.new("blake2b", digest_size=32)
    hasher.update(encoded)
    return hasher.digest()


def _sign_zome_call(sk, call_unsigned: dict) -> bytes:
    """Sign a ZomeCallUnsigned dict; returns 64-byte Ed25519 signature."""
    if sk is None:
        return bytes(64)
    digest = _hash_zome_call(call_unsigned)
    signed = sk.sign(digest)
    return bytes(signed.signature)  # first 64 bytes are the signature



# ─────────────────────────────────────────────────────────────────────────────
# Low-level message framing
# ─────────────────────────────────────────────────────────────────────────────


def _encode_request(request_id: int, payload: Any) -> bytes:
    """
    Encode a Holochain conductor wire request (msgpack).

    Outer envelope: {id: uint, type: "request", data: <msgpack-bytes of AppRequest>}

    Verified against @holochain/client 0.17.x (Holochain 0.3.x):
      - The outer 'data' field is a nested msgpack blob of the AppRequest enum.
      - AppRequest is internally tagged: {type: "app_info"} or
        {type: "call_zome", data: {...}}  (serde tag+content attributes)
    """
    inner = msgpack.packb(payload, use_bin_type=True)
    envelope = {
        "id":   request_id,
        "type": "request",
        "data": inner,
    }
    return msgpack.packb(envelope, use_bin_type=True)


def _decode_response(raw: bytes) -> tuple[int, Any]:
    """
    Decode a Holochain conductor wire response.

    Outer envelope: {id: uint, type: "response", data: <msgpack-bytes of AppResponse>}
    Inner AppResponse (Holochain 0.3.x): {type: "app_info"|"zome_call"|"error", data: ...}
    """
    envelope = msgpack.unpackb(raw, raw=False)
    request_id = envelope.get("id", -1)
    raw_data   = envelope.get("data", b"")

    # 'data' is always a nested msgpack blob from Holochain 0.3.x
    if isinstance(raw_data, (bytes, bytearray)) and raw_data:
        data = msgpack.unpackb(raw_data, raw=False)
    else:
        data = raw_data

    return request_id, data


# ─────────────────────────────────────────────────────────────────────────────
# Single conductor connection
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConductorConnection:
    """
    Manages a single WebSocket connection to one Holochain conductor's
    App API endpoint (e.g. ws://localhost:9001).

    Uses websockets.asyncio.client (websockets ≥ 12.0) — NOT the legacy shim.
    The asyncio-native API is required for correct binary framing with Holochain
    0.3.x conductors; the legacy shim causes immediate CLOSE 1005 disconnects.
    """
    url:              str
    installed_app_id: str
    cell_role_name:   str
    admin_url:        Optional[str] = field(default=None)

    _ws:              Optional[WebSocketClientProtocol] = field(default=None, init=False, repr=False)
    _cell_id:         Optional[list]             = field(default=None, init=False, repr=False)
    _pending:         dict[int, asyncio.Future]  = field(default_factory=dict, init=False, repr=False)
    _reader_task:     Optional[asyncio.Task]      = field(default=None, init=False, repr=False)
    # Per-instance counter — avoids global state leak across tests / connections
    _request_counter: int                         = field(default=0, init=False, repr=False)
    connected:        bool                        = field(default=False, init=False)
    label:            str                         = field(default="", init=False)
    # Signing key for ZomeCall signatures (Holochain 0.3.x requires signed calls)
    _signing_key:     Any                         = field(default=None, init=False, repr=False)
    _cap_secret:      Optional[bytes]             = field(default=None, init=False, repr=False)
    _agent_pubkey:    Optional[bytes]             = field(default=None, init=False, repr=False)

    def _next_request_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    async def connect(self) -> bool:
        """
        Open WebSocket connection, authenticate via Admin, and fetch cell_id via app_info.
        Returns True on success, False if the conductor is unreachable.
        """
        # Generate an ephemeral Ed25519 signing key for ZomeCall signatures
        self._signing_key = _new_signing_key()
        if self._signing_key is not None:
            self._agent_pubkey = _signing_key_to_agent_pubkey(self._signing_key)
            self._cap_secret = os.urandom(_CAP_SECRET_BYTES)
        else:
            self._agent_pubkey = None
            self._cap_secret = bytes(_CAP_SECRET_BYTES)

        try:
            token = None
            if self.admin_url:
                # 1. Fetch authentication token AND grant capability via Admin Interface
                try:
                     async with websockets.connect(
                        self.admin_url, ping_interval=None, open_timeout=5, origin="http://localhost"
                    ) as admin_ws:
                        # 1a. Issue app authentication token
                        admin_req = {
                            "type": "issue_app_authentication_token",
                            "data": {"installed_app_id": self.installed_app_id}
                        }
                        envelope = {
                            "id": 1,
                            "type": "request",
                            "data": msgpack.packb(admin_req, use_bin_type=True)
                        }
                        await admin_ws.send(msgpack.packb(envelope, use_bin_type=True))
                        resp_bytes = await admin_ws.recv()
                        resp_data = msgpack.unpackb(resp_bytes, raw=False)
                        inner_resp = msgpack.unpackb(resp_data["data"], raw=False)
                        if inner_resp.get("type") == "app_authentication_token_issued":
                            token = inner_resp["data"]["token"]
                        else:
                            logger.error(f"Failed to issue token: {inner_resp}")

                        # --- still inside admin_ws ---
                        # 1b. Connect app WS and get cell_id
                        self._ws = await websockets.connect(
                            self.url,
                            ping_interval=30,
                            open_timeout=10,
                            origin="http://localhost",
                        )
                        if token:
                            try:
                                auth_frame = {
                                    "type": "authenticate",
                                    "data": msgpack.packb({"token": token}, use_bin_type=True)
                                }
                                await self._ws.send(msgpack.packb(auth_frame, use_bin_type=True))
                                await asyncio.sleep(0.05)
                            except Exception as e:
                                logger.error(f"Failed to send authenticate frame: {e}")

                        self._reader_task = asyncio.create_task(self._reader_loop())

                        app_info_resp = await self._send({"type": "app_info"})
                        if isinstance(app_info_resp, dict) and app_info_resp.get("type") == "app_info":
                            app_info = app_info_resp.get("data", app_info_resp)
                        elif isinstance(app_info_resp, dict) and "app_info" in app_info_resp:
                            app_info = app_info_resp["app_info"]
                        else:
                            app_info = app_info_resp

                        cell = self._extract_cell(app_info)
                        if cell is not None:
                            self._cell_id = cell

                        # 1c. Grant cap on the still-open admin WS connection
                        if self._cell_id is not None and self._agent_pubkey is not None and self._cap_secret is not None:
                            # Rust serde DEFAULT externally-tagged enum format (NO custom serde attrs):
                            #   GrantedFunctions::All  → "All"          (plain string, NOT {"type":"all"})
                            #   CapAccess::Assigned    → {"Assigned": {"secret":..,"assignees":[..]}}
                            # ZomeCallCapGrant struct field order: tag, access, functions
                            grant_req = {
                                "type": "grant_zome_call_capability",
                                "data": {
                                    "cell_id": self._cell_id,
                                    "cap_grant": {
                                        "tag": "zome-call-signing-key",
                                        "access": {
                                            "Assigned": {
                                                "secret": self._cap_secret,
                                                "assignees": [self._agent_pubkey],
                                            }
                                        },
                                        "functions": "All",
                                    },
                                },
                            }
                            env2 = {
                                "id": 2,
                                "type": "request",
                                "data": msgpack.packb(grant_req, use_bin_type=True),
                            }
                            await admin_ws.send(msgpack.packb(env2, use_bin_type=True))
                            gr_bytes = await admin_ws.recv()
                            gr_data  = msgpack.unpackb(gr_bytes, raw=False)
                            gr_inner = msgpack.unpackb(gr_data.get("data", b""), raw=False)
                            if isinstance(gr_inner, dict) and gr_inner.get("type") == "zome_call_capability_granted":
                                logger.info("[%s] ✓ CapGrant issued for ephemeral signing key", self.url)
                            else:
                                logger.warning("[%s] CapGrant response: %s", self.url, gr_inner)

                except Exception as e:
                    logger.error(f"Admin WS error on {self.admin_url}: {e}")
                    # Continue — _ws and _cell_id may still be set from inside the try

            # ── If no admin_url: connect app WS directly ──────────────────────────
            if self._ws is None:
                try:
                    self._ws = await websockets.connect(
                        self.url,
                        ping_interval=30,
                        open_timeout=10,
                        origin="http://localhost",
                    )
                    self._reader_task = asyncio.create_task(self._reader_loop())
                    app_info_resp = await self._send({"type": "app_info"})
                    if isinstance(app_info_resp, dict) and app_info_resp.get("type") == "app_info":
                        app_info = app_info_resp.get("data", app_info_resp)
                    elif isinstance(app_info_resp, dict) and "app_info" in app_info_resp:
                        app_info = app_info_resp["app_info"]
                    else:
                        app_info = app_info_resp
                    cell = self._extract_cell(app_info)
                    if cell is not None:
                        self._cell_id = cell
                except Exception as exc:
                    logger.warning("[%s] Direct app WS connect failed: %s", self.url, exc)
                    self.connected = False
                    return False

            if self._cell_id is None:
                logger.warning("[%s] No cell_id after connect", self.url)
                self.connected = False
                return False

            self.connected = True
            logger.info("[%s] Connected — cell_id obtained", self.url)
            return True

        except Exception as exc:
            logger.warning("[%s] Connection failed: %s", self.url, exc)
            self.connected = False
            return False

    async def disconnect(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self.connected = False

    # ── Low-level send/receive ────────────────────────────────────────────

    async def _send(self, payload: dict, timeout: float = 30.0) -> Any:
        if not self._ws:
            raise RuntimeError(f"Not connected to {self.url}")
        request_id = self._next_request_id()
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future
        raw = _encode_request(request_id, payload)
        await self._ws.send(raw)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise TimeoutError(f"Conductor {self.url} did not respond within {timeout}s")

    async def _reader_loop(self) -> None:
        """Background task: reads binary responses and resolves pending futures."""
        try:
            async for raw_message in self._ws:  # type: ignore[union-attr]
                if isinstance(raw_message, (bytes, bytearray)):
                    try:
                        req_id, data = _decode_response(bytes(raw_message))
                        if req_id in self._pending:
                            fut = self._pending.pop(req_id)
                            if not fut.done():
                                fut.set_result(data)
                    except Exception as e:
                        logger.debug("Failed to decode conductor message: %s", e)
                # text frames are not used by Holochain; ignore silently
        except Exception as exc:
            logger.warning("[%s] Reader loop terminated: %s", self.url, exc)
            self.connected = False
            # Fail all pending futures so callers don't hang indefinitely
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(ConnectionError(f"Conductor {self.url} disconnected"))
            self._pending.clear()

    def _extract_cell(self, app_info: Any) -> Optional[list]:
        """
        Navigate app_info to find the cell_id for our role.

        Holochain 0.3.6 actual shape — cell_info is directly on app_info, no 'app' wrapper:
          {
            "installed_app_id": "d-cloud",
            "cell_info": {
              "file_storage": [
                {"provisioned": {"cell_id": [<dna_hash>, <agent_key>], ...}}
              ]
            },
            "status": {"running": null}
          }
        """
        try:
            if app_info is None:
                logger.debug("cell extraction error: app_info is None")
                return None

            # Unwrap {"type": "app_info", "data": <actual info>} if present
            if isinstance(app_info, dict) and app_info.get("type") == "app_info":
                app_info = app_info.get("data", app_info)

            if not isinstance(app_info, dict):
                logger.debug("cell extraction error: app_info is not a dict: %r", app_info)
                return None

            # cell_info is directly on app_info in 0.3.6 — no 'app' wrapper
            cell_info = app_info.get("cell_info", {})
            if not cell_info:
                logger.debug("[%s] app_info has no cell_info. Keys: %s",
                             self.url, list(app_info.keys()))
                return None

            # Try configured role name first, then fall back to first available role
            role_cells = cell_info.get(self.cell_role_name, [])
            if not role_cells:
                available = list(cell_info.keys())
                logger.debug("[%s] Role '%s' not found. Available: %s",
                             self.url, self.cell_role_name, available)
                if available:
                    role_cells = cell_info[available[0]]

            if not role_cells:
                return None

            # CellInfo is an externally-tagged enum: {"provisioned": {...}}
            first = role_cells[0]
            for variant in ("provisioned", "cloned", "stem"):
                if variant in first:
                    cell_id = first[variant].get("cell_id")
                    if cell_id:
                        return cell_id

            return first.get("cell_id")

        except Exception as e:
            logger.debug("cell extraction error: %s | app_info was: %r", e, app_info)
            return None

    # ── Public: call a zome function ─────────────────────────────────────

    async def call_zome(
        self,
        zome_name: str,
        fn_name: str,
        payload: Any,
        timeout: float = 60.0,
    ) -> Any:
        """
        Call a coordinator zome function.

        Holochain 0.3.x requires ZomeCalls to be cryptographically signed:
          1. Build ZomeCallUnsigned (all fields except signature)
          2. Compute blake3(msgpack(ZomeCallUnsigned))
          3. Sign the digest with the ephemeral Ed25519 keypair
          4. Send call_zome with the full signed payload

        Returns the decoded msgpack response from the zome function.
        """
        if not self.connected or self._cell_id is None:
            raise RuntimeError(f"Conductor {self.url} is not connected")

        # ExternIO: the zome function input is msgpack-encoded bytes
        encoded_payload = msgpack.packb(payload, use_bin_type=True)

        # Determine provenance — use our ephemeral signing key's pubkey if available,
        # otherwise fall back to the agent pubkey from the cell_id
        agent_pubkey = self._agent_pubkey if self._agent_pubkey is not None else bytes(self._cell_id[1])
        cap_secret = self._cap_secret if self._cap_secret is not None else bytes(_CAP_SECRET_BYTES)

        # Build nonce and expiry (Holochain 0.3.x requirement)
        nonce = os.urandom(_NONCE_BYTES)
        expires_at = int(time.time() * 1_000_000) + _NONCE_EXPIRY_MICROS  # microseconds

        # ZomeCallUnsigned — MUST be in EXACT field order matching the Rust struct:
        # provenance, cell_id, zome_name, fn_name, cap_secret, payload, nonce, expires_at
        # (Serde serializes struct fields in declaration order; msgpack is positional/ordered)
        call_unsigned = {
            "provenance": agent_pubkey,
            "cell_id":    self._cell_id,
            "zome_name":  zome_name,
            "fn_name":    fn_name,
            "cap_secret": cap_secret,
            "payload":    encoded_payload,
            "nonce":      nonce,
            "expires_at": expires_at,
        }

        # Sign the ZomeCallUnsigned with our ephemeral key
        signature = _sign_zome_call(self._signing_key, call_unsigned)

        # Full signed ZomeCall (add signature field)
        zome_call_signed = {**call_unsigned, "signature": signature}

        # Wrap in the AppRequest envelope
        call_data = {
            "type": "call_zome",
            "data": zome_call_signed,
        }

        response = await self._send(call_data, timeout=timeout)
        return self._unwrap_zome_result(response)


    @staticmethod
    def _unwrap_zome_result(response: Any) -> Any:
        """
        Holochain 0.3.x AppResponse uses internally-tagged enum format:
          {"type": "zome_call", "data": <ExternIO bytes>}  — success
          {"type": "error",     "data": {message, ...}}    — zome error

        ExternIO is the raw msgpack-encoded output of the zome function.
        We decode it one more time to get the actual return value.
        """
        if not isinstance(response, dict):
            return response

        resp_type = response.get("type", "")
        resp_data = response.get("data")

        if resp_type == "error":
            msg = resp_data.get("message", str(resp_data)) if isinstance(resp_data, dict) else str(resp_data)
            raise RuntimeError(f"Zome error: {msg}")

        if resp_type == "zome_call":
            # ExternIO is bytes — decode to get the actual zome output
            if isinstance(resp_data, (bytes, bytearray)) and resp_data:
                decoded = msgpack.unpackb(resp_data, raw=False)
            else:
                decoded = resp_data
                
            if isinstance(decoded, dict):
                if "Ok" in decoded:
                    return decoded["Ok"]
                if "Err" in decoded:
                    raise RuntimeError(f"Zome error: {decoded['Err']}")
            return decoded

        # Fallback: older Ok/Err format (pre-0.3.x or sandbox wrappers)
        if "Ok" in response:
            raw = response["Ok"]
            if isinstance(raw, (bytes, bytearray)) and raw:
                return msgpack.unpackb(raw, raw=False)
            return raw
        if "Err" in response:
            raise RuntimeError(f"Zome error: {response['Err']}")

        return response


# ─────────────────────────────────────────────────────────────────────────────
# Multi-conductor pool (redundancy + failover)
# ─────────────────────────────────────────────────────────────────────────────

class ConductorPool:
    """
    Manages connections to multiple Holochain conductors (Node1, Node2, Node3).

    On upload: calls are made on ALL healthy conductors in parallel so the DHT
    receives chunks via multiple agents, maximising replication.

    On retrieval: tries conductors in order; falls back to the next if one fails.
    This is the bridge-layer redundancy that survives node failures.
    """

    def __init__(
        self,
        conductor_urls: list[str],
        installed_app_id: str,
        cell_role_name: str,
        admin_urls: Optional[list[str]] = None,
    ) -> None:
        self._installed_app_id = installed_app_id
        self._cell_role_name   = cell_role_name
        self.conductors: list[ConductorConnection] = [
            ConductorConnection(
                url=url,
                installed_app_id=installed_app_id,
                cell_role_name=cell_role_name,
                admin_url=admin_urls[i] if admin_urls and i < len(admin_urls) else None,
            )
            for i, url in enumerate(conductor_urls)
        ]

    async def connect_all(self) -> None:
        """Connect to all conductors concurrently. Logs which ones failed."""
        results = await asyncio.gather(
            *[c.connect() for c in self.conductors],
            return_exceptions=True,
        )
        for conn, ok in zip(self.conductors, results):
            if ok is True:
                logger.info("✓ Connected to conductor at %s", conn.url)
            else:
                logger.warning("✗ Could not connect to conductor at %s — %s", conn.url, ok)

    def healthy(self) -> list[ConductorConnection]:
        """Return all conductors that are currently connected."""
        return [c for c in self.conductors if c.connected]

    @property
    def connected_count(self) -> int:
        return len(self.healthy())

    async def call_zome_with_retry(
        self,
        zome_name: str,
        fn_name: str,
        payload: Any,
        timeout: float = 60.0,
    ) -> Any:
        """
        Try each healthy conductor in order until one succeeds.
        Raises RuntimeError if ALL conductors fail — surfaces as HTTP 503.
        """
        errors: list[str] = []
        for conductor in self.healthy():
            try:
                result = await conductor.call_zome(
                    zome_name, fn_name, payload, timeout=timeout
                )
                return result
            except Exception as exc:
                logger.warning(
                    "Conductor %s failed for %s.%s: %s",
                    conductor.url, zome_name, fn_name, exc
                )
                errors.append(f"{conductor.url}: {exc}")

        raise RuntimeError(
            f"All conductors failed for {zome_name}.{fn_name}. "
            f"Errors: {'; '.join(errors)}"
        )

    async def call_zome_on_all(
        self,
        zome_name: str,
        fn_name: str,
        payload: Any,
        timeout: float = 60.0,
    ) -> list[Any]:
        """
        Call a zome function on ALL healthy conductors concurrently.
        Used for uploads to maximise DHT replication immediately.
        Returns results from all conductors that succeed (ignores failures).
        """
        tasks = [
            conductor.call_zome(zome_name, fn_name, payload, timeout=timeout)
            for conductor in self.healthy()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successes = []
        errors = []
        for r in results:
            if isinstance(r, Exception):
                errors.append(str(r))
                logger.error(f"Broadcast zome call failed: {r}")
            else:
                successes.append(r)
        
        if not successes:
            raise RuntimeError(
                f"All conductors failed on broadcast call to {zome_name}.{fn_name}. Errors: {'; '.join(errors)}"
            )
        return successes

    async def disconnect_all(self) -> None:
        await asyncio.gather(*[c.disconnect() for c in self.conductors])
