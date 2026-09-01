import base64
import hashlib
import hmac
import json
import time
import unittest

from chat_service.auth import AuthError, IdentityVerifier


SECRET = b"0123456789abcdef0123456789abcdef"


def token(payload, secret=SECRET):
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).rstrip(b"=")
    signature = hmac.new(secret, encoded, hashlib.sha256).digest()
    return "v1." + encoded.decode() + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def claims(**overrides):
    now = int(time.time())
    payload = {
        "sub": "user-1", "name": "Ada", "iss": "librenms",
        "aud": "ai-assistant", "iat": now, "exp": now + 3600,
    }
    payload.update(overrides)
    return payload


class IdentityVerifierTests(unittest.TestCase):
    def setUp(self):
        self.now = 2_000_000_000
        self.verifier = IdentityVerifier(SECRET, clock=lambda: self.now)

    def test_accepts_well_signed_required_claims(self):
        identity = self.verifier.verify(token(claims(iat=self.now, exp=self.now + 3600)))
        self.assertEqual((identity.sub, identity.name), ("user-1", "Ada"))

    def test_rejects_tampered_signature_and_missing_claims(self):
        with self.assertRaises(AuthError):
            self.verifier.verify(token(claims(iat=self.now, exp=self.now + 3600)) + "x")
        with self.assertRaises(AuthError):
            self.verifier.verify(token({"sub": "user-1"}))

    def test_allows_iat_thirty_seconds_future_but_not_thirty_one(self):
        accepted = token(claims(iat=self.now + 30, exp=self.now + 3630))
        self.assertEqual(self.verifier.verify(accepted).sub, "user-1")
        rejected = token(claims(iat=self.now + 31, exp=self.now + 3631))
        with self.assertRaises(AuthError):
            self.verifier.verify(rejected)

    def test_requires_exact_lifetime_and_strict_expiry(self):
        with self.assertRaises(AuthError):
            self.verifier.verify(token(claims(iat=self.now - 3600, exp=self.now)))
        with self.assertRaises(AuthError):
            self.verifier.verify(token(claims(iat=self.now, exp=self.now + 3599)))

