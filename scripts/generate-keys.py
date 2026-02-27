#!/usr/bin/env python3
"""
D-Cloud Key Generation Utility
================================
Generates and saves the two keypairs needed by the FastAPI bridge:

  1. Ed25519 signing keypair  → api-bridge/keys/bridge_ed25519.key
     Used to sign every chunk before upload. Stored in FileChunk.signer_pubkey.

  2. X25519 recipient keypair → api-bridge/keys/recipient_x25519.key
     Used for DEK wrapping. Only the holder of this private key can decrypt files.

Run once before starting the bridge for the first time.
If keys already exist, displays their public key fingerprints without overwriting.

Locked version: cryptography==42.0.5
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "api-bridge"))

import crypto as cr


def main() -> None:
    signing_path   = cr.SIGNING_KEY_PATH
    recipient_path = cr.RECIPIENT_KEY_PATH

    print("D-Cloud Key Generator")
    print("=" * 50)

    # Ed25519 signing keypair
    if signing_path.exists():
        kp = cr.load_or_create_signing_keypair()
        print(f"✅  Ed25519 signing key already exists")
        print(f"    Path:   {signing_path}")
        print(f"    Pubkey: {kp.pubkey_hex}")
    else:
        kp = cr.generate_signing_keypair()
        print(f"🔑  Generated Ed25519 signing keypair")
        print(f"    Path:   {signing_path}")
        print(f"    Pubkey: {kp.pubkey_hex}")
        print(f"    ⚠️  Keep the private key file secret — it signs all chunk uploads.")

    print()

    # X25519 recipient keypair
    if recipient_path.exists():
        rp = cr.load_or_create_recipient_keypair()
        print(f"✅  X25519 recipient key already exists")
        print(f"    Path:   {recipient_path}")
        print(f"    Pubkey: {rp.pubkey_hex}")
    else:
        rp = cr.generate_recipient_keypair()
        print(f"🔑  Generated X25519 recipient keypair")
        print(f"    Path:   {recipient_path}")
        print(f"    Pubkey: {rp.pubkey_hex}")
        print(f"    ⚠️  Keep the private key file secret — it decrypts all files.")

    print()
    print("=" * 50)
    print("Keys saved. Copy these public keys into your .env or share them")
    print("with parties who need to upload files to your node.")


if __name__ == "__main__":
    main()
