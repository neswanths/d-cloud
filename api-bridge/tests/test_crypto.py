"""
test_crypto.py — Unit tests for the D-Cloud cryptographic utilities.

Locked versions: pytest==8.1.1 | cryptography==42.0.5
Run with: pytest tests/test_crypto.py -v
"""

import os
import sys

import pytest

# Make crypto importable from sibling directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import crypto as cr


# ─────────────────────────────────────────────────────────────────────────────
# Ed25519 signing
# ─────────────────────────────────────────────────────────────────────────────

class TestEd25519:
    def setup_method(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        self.private_key = Ed25519PrivateKey.generate()
        public_key       = self.private_key.public_key()
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        self.pubkey_hex = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    def test_sign_and_verify_roundtrip(self):
        chunk_hash = "abc123def456"
        signature  = cr.sign_chunk(chunk_hash, self.private_key)
        assert cr.verify_chunk_signature(chunk_hash, signature, self.pubkey_hex) is True

    def test_wrong_message_fails(self):
        sig = cr.sign_chunk("real_hash", self.private_key)
        assert cr.verify_chunk_signature("tampered_hash", sig, self.pubkey_hex) is False

    def test_corrupted_signature_fails(self):
        chunk_hash = "abc123"
        sig = cr.sign_chunk(chunk_hash, self.private_key)
        bad_sig = "00" * 64   # 64 zero bytes
        assert cr.verify_chunk_signature(chunk_hash, bad_sig, self.pubkey_hex) is False

    def test_wrong_pubkey_fails(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        other_pub = Ed25519PrivateKey.generate().public_key()
        other_hex = other_pub.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        sig = cr.sign_chunk("hash", self.private_key)
        assert cr.verify_chunk_signature("hash", sig, other_hex) is False


# ─────────────────────────────────────────────────────────────────────────────
# AES-256-GCM encryption / decryption
# ─────────────────────────────────────────────────────────────────────────────

class TestAESGCM:
    def test_encrypt_decrypt_roundtrip(self):
        dek       = cr.generate_dek()
        plaintext = b"Hello, decentralised world!"
        ct, nonce = cr.encrypt_chunk(dek, plaintext)
        recovered = cr.decrypt_chunk(dek, nonce, ct)
        assert recovered == plaintext

    def test_different_nonce_each_call(self):
        dek = cr.generate_dek()
        _, n1 = cr.encrypt_chunk(dek, b"same data")
        _, n2 = cr.encrypt_chunk(dek, b"same data")
        assert n1 != n2, "Nonces must be unique per encryption"

    def test_tampered_ciphertext_rejected(self):
        from cryptography.exceptions import InvalidTag
        dek = cr.generate_dek()
        ct, nonce = cr.encrypt_chunk(dek, b"secret")
        bad_ct = bytes([ct[0] ^ 0xFF]) + ct[1:]   # flip first byte
        with pytest.raises(InvalidTag):
            cr.decrypt_chunk(dek, nonce, bad_ct)

    def test_wrong_dek_rejected(self):
        from cryptography.exceptions import InvalidTag
        dek1 = cr.generate_dek()
        dek2 = cr.generate_dek()
        ct, nonce = cr.encrypt_chunk(dek1, b"private data")
        with pytest.raises(InvalidTag):
            cr.decrypt_chunk(dek2, nonce, ct)

    def test_dek_is_32_bytes(self):
        dek = cr.generate_dek()
        assert len(dek) == 32


# ─────────────────────────────────────────────────────────────────────────────
# X25519 DEK wrapping / unwrapping
# ─────────────────────────────────────────────────────────────────────────────

class TestDEKWrapping:
    def setup_method(self):
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        self.priv = X25519PrivateKey.generate()
        self.pub_hex = self.priv.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        ).hex()

    def test_wrap_unwrap_roundtrip(self):
        dek = cr.generate_dek()
        wrapped = cr.wrap_dek(dek, self.pub_hex)
        recovered = cr.unwrap_dek(wrapped, self.priv)
        assert recovered == dek

    def test_wrapped_dek_correct_length(self):
        dek = cr.generate_dek()
        wrapped_hex = cr.wrap_dek(dek, self.pub_hex)
        assert len(bytes.fromhex(wrapped_hex)) == cr.WRAPPED_LEN

    def test_wrong_recipient_key_fails(self):
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from cryptography.exceptions import InvalidTag
        dek = cr.generate_dek()
        wrapped = cr.wrap_dek(dek, self.pub_hex)
        wrong_priv = X25519PrivateKey.generate()
        with pytest.raises((InvalidTag, Exception)):
            cr.unwrap_dek(wrapped, wrong_priv)

    def test_tampered_wrapped_dek_rejected(self):
        from cryptography.exceptions import InvalidTag
        dek = cr.generate_dek()
        wrapped_hex = cr.wrap_dek(dek, self.pub_hex)
        # Flip a byte in the ciphertext region
        payload = bytearray(bytes.fromhex(wrapped_hex))
        payload[60] ^= 0xFF
        with pytest.raises((InvalidTag, Exception)):
            cr.unwrap_dek(payload.hex(), self.priv)


# ─────────────────────────────────────────────────────────────────────────────
# Hashing utilities
# ─────────────────────────────────────────────────────────────────────────────

class TestHashing:
    def test_sha256_known_value(self):
        # SHA-256 of empty string is well-known
        result = cr.sha256_hex(b"")
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_root_hash_order_matters(self):
        hashes = ["aaa", "bbb", "ccc"]
        r1 = cr.compute_root_hash(hashes)
        r2 = cr.compute_root_hash(["ccc", "aaa", "bbb"])
        assert r1 != r2, "Root hash must be order-dependent"

    def test_root_hash_single_chunk(self):
        h = cr.sha256_hex(b"test")
        root = cr.compute_root_hash([h])
        assert isinstance(root, str) and len(root) == 64


# ─────────────────────────────────────────────────────────────────────────────
# Full pipeline: prepare_chunks + verify_and_decrypt_chunk
# ─────────────────────────────────────────────────────────────────────────────

class TestFullPipeline:
    def setup_method(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PublicFormat, PrivateFormat, NoEncryption
        )
        priv = Ed25519PrivateKey.generate()
        pub  = priv.public_key()
        pubhex = pub.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        self.signing = cr.SigningKeyPair(priv, pub, pubhex)

    def test_single_chunk_roundtrip(self):
        data = b"A" * 100
        dek  = cr.generate_dek()
        bundles = cr.prepare_chunks(data, dek, self.signing, chunk_size=200)
        assert len(bundles) == 1
        pt = cr.verify_and_decrypt_chunk(
            bundles[0].ciphertext,
            bundles[0].nonce_hex,
            bundles[0].chunk_hash,
            bundles[0].signature,
            bundles[0].signer_pubkey,
            dek,
        )
        assert pt == data

    def test_multi_chunk_roundtrip(self):
        data = os.urandom(200 * 1024)   # 200 KB → 4 chunks at 64 KB
        dek  = cr.generate_dek()
        bundles = cr.prepare_chunks(data, dek, self.signing, chunk_size=65536)
        assert len(bundles) == 4

        recovered = b""
        for bundle in bundles:
            pt = cr.verify_and_decrypt_chunk(
                bundle.ciphertext, bundle.nonce_hex,
                bundle.chunk_hash, bundle.signature,
                bundle.signer_pubkey, dek,
            )
            recovered += pt
        assert recovered == data

    def test_tampered_chunk_rejected(self):
        data = b"sensitive"
        dek  = cr.generate_dek()
        [b] = cr.prepare_chunks(data, dek, self.signing, chunk_size=65536)
        bad_ct = bytes([b.ciphertext[0] ^ 0xFF]) + b.ciphertext[1:]
        with pytest.raises(ValueError, match="hash mismatch"):
            cr.verify_and_decrypt_chunk(
                bad_ct, b.nonce_hex, b.chunk_hash,
                b.signature, b.signer_pubkey, dek,
            )
