"""Contrato de credenciales: cuenta email/password, proxy username/session token."""
import json
import unittest

from account_auth import AccountClient, AccountAuthError, AccountSession, API_PATH, validate_login
from proxycore import Upstream, _inject_proxy_auth


class TestAccountAuth(unittest.TestCase):
    def test_login_sends_exact_email_and_password_json(self):
        calls = []
        def transport(url, raw, timeout):
            calls.append((url, json.loads(raw), timeout))
            return 200, json.dumps({
                "sessionAuthToken": "session-secret", "isPremium": False,
                "username": "my-1vpn-username", "email": "user@example.com"
            }).encode()
        session = AccountClient(transport=transport, domains=("1vpn.org",)).login("  user@example.com ", " P@ss word ")
        self.assertEqual(calls, [("https://1vpn.org" + API_PATH,
                                  {"email": "user@example.com", "password": " P@ss word "}, 10.0)])
        self.assertEqual(session.email, "user@example.com")
        self.assertEqual(session.username, "my-1vpn-username")
        self.assertFalse(session.is_premium)
        self.assertNotIn("session-secret", repr(session))

    def test_two_factor_sends_token_as_separate_json_field(self):
        seen = []
        def transport(url, raw, timeout):
            seen.append(json.loads(raw))
            return 200, b'{"sessionAuthToken":"token","isPremium":true}'
        session = AccountClient(transport=transport, domains=("1vpn.org",)).login("a@b.com", "secreT", " 654321 ")
        self.assertEqual(seen[0], {"email": "a@b.com", "password": "secreT", "token": "654321"})
        self.assertTrue(session.is_premium)
        self.assertEqual(session.tier, "Premium")

    def test_2fa_required_is_not_treated_as_bad_password(self):
        client = AccountClient(transport=lambda *_: (403, b'{"error":"2FA required","code":1001}'), domains=("1vpn.org",))
        with self.assertRaises(AccountAuthError) as exc:
            client.login("user@example.org", "validpassword")
        self.assertEqual(exc.exception.reason, "two_factor_required")

    def test_account_rejection_does_not_retry_credentials_to_backups(self):
        seen = []
        def transport(url, raw, timeout):
            seen.append(url)
            return 401, b'{"detail":"invalid credentials"}'
        client = AccountClient(transport=transport)
        with self.assertRaises(AccountAuthError) as exc:
            client.login("user@example.org", "incorrect")
        self.assertEqual(exc.exception.reason, "rejected")
        self.assertEqual(len(seen), 1)

    def test_network_failure_only_retries_allowlisted_domains(self):
        urls = []
        def transport(url, raw, timeout):
            urls.append(url)
            if len(urls) == 1: raise TimeoutError("the_password_was_secret")
            return 200, b'{"sessionAuthToken":"t","isPremium":false}'
        session = AccountClient(transport=transport, domains=("1vpn.org", "1vpn.co")).login("u@e.org", "secret")
        self.assertEqual(len(urls), 2)
        self.assertIn("1vpn.co", urls[1])
        self.assertEqual(session.tier, "Free")

    def test_unavailable_not_reported_as_wrong_password(self):
        client = AccountClient(transport=lambda *_: (_ for _ in ()).throw(TimeoutError("secret")), domains=("1vpn.org",))
        with self.assertRaises(AccountAuthError) as exc:
            client.login("u@e.org", "password")
        self.assertEqual(exc.exception.reason, "unavailable")
        self.assertNotIn("password", str(exc.exception).lower())

    def test_invalid_email_rejected_before_network(self):
        calls = []
        client = AccountClient(transport=lambda *_: calls.append(1))
        for bad in ("username", "", " user @example.com ", "x@y.com\r\nInjected: header"):
            with self.subTest(bad=bad), self.assertRaises(AccountAuthError):
                client.login(bad, "secret")
        self.assertEqual(calls, [])

    def test_empty_password_rejected_before_network(self):
        with self.assertRaises(AccountAuthError) as exc:
            validate_login("me@example.org", "")
        self.assertEqual(exc.exception.reason, "missing_password")

    def test_unexpected_success_payload_rejected(self):
        client = AccountClient(transport=lambda *_: (200, b'{"sessionAuthToken":"x"}'), domains=("1vpn.org",))
        with self.assertRaises(AccountAuthError) as exc:
            client.login("me@example.org", "password")
        self.assertEqual(exc.exception.reason, "malformed")

    def test_html_403_is_not_wrong_password(self):
        client = AccountClient(transport=lambda *_: (403, b'<html>Access denied</html>'), domains=("1vpn.org",))
        with self.assertRaises(AccountAuthError) as exc:
            client.login("me@example.org", "password")
        self.assertEqual(exc.exception.reason, "unavailable")

    def test_body_larger_than_limit_not_accepted(self):
        client = AccountClient(transport=lambda *_: (200, b'x'*70000), domains=("1vpn.org",))
        with self.assertRaises(AccountAuthError) as exc:
            client.login("me@example.org", "password")
        self.assertEqual(exc.exception.reason, "unavailable")

    def test_domains_are_restricted(self):
        with self.assertRaises(ValueError): AccountClient(domains=("evil.example.org",))
        with self.assertRaises(ValueError): AccountClient(domains=())

    def test_password_is_never_used_as_proxy_password_automatically(self):
        account = AccountSession("owner@example.org", "user1", True, "account-token")
        proxy = Upstream("proxy.example.org", 443, "proxy-user", "proxy-secret")
        header = _inject_proxy_auth(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n", proxy)
        self.assertNotIn(account.email.encode(), header)
        self.assertNotIn(b"account-token", header)
        self.assertNotIn(b"owner@example.org", header)
        self.assertIn(b"Proxy-Authorization", header)


if __name__ == "__main__":
    unittest.main()
