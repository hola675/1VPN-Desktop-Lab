"""No real credentials or network needed for Premium consent bridge tests."""
import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from account_auth import AccountSession
from premium_bridge import PremiumBrowserBridge, parse_browser_session

ORIGIN = "chrome-extension://" + "a" * 32
MOCK = {
    "username": "test-proxy-user",
    "sessionAuthToken": "FAKE_TOKEN_NOT_A_REAL_SECRET_012345",
    "isPremium": True,
    "locations": [
        {"cityCode": "sgp", "hosts": [
            {"hostname": "premium-singapore-https-1.cloudburstcdn.com", "port": 443},
            {"hostname": "127.0.0.1", "port": 443},
            {"hostname": "localhost", "port": 443},
            {"hostname": "example.org", "port": 80},
        ]},
        {"cityCode": "fra", "hosts": [
            {"hostname": "premium-frankfurt-https-1.cloudflingcdn.com"}
        ]},
    ],
}


class TestPremiumParsing(unittest.TestCase):
    def test_valid_session_and_no_secret_in_repr(self):
        result = parse_browser_session(MOCK)
        self.assertIsInstance(result, AccountSession)
        self.assertEqual(result.source, "browser_web")
        self.assertTrue(result.is_premium)
        self.assertEqual(len(result.proxy_locations), 2)
        self.assertIn(("sgp", "premium-singapore-https-1.cloudburstcdn.com", 443),
                      result.proxy_locations)
        self.assertNotIn("FAKE_TOKEN", repr(result))

    def test_rejects_free_missing_token_and_missing_servers(self):
        for values in ({"isPremium": False},
                       {"sessionAuthToken": ""},
                       {"locations": []},
                       {"locations": [{"cityCode": "sgp", "hosts": [{"hostname": "127.0.0.1"}]}]}):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    parse_browser_session({**MOCK, **values})

    def test_proxy_upstream_repr_never_shows_premium_password(self):
        from proxycore import Upstream
        upstream = Upstream("proxy.example.org", 443, "web-user", "SECRET_WEB_TOKEN")
        self.assertNotIn("SECRET_WEB_TOKEN", repr(upstream))
        self.assertEqual(upstream.password, "SECRET_WEB_TOKEN")

    def test_xray_session_does_not_get_browser_source(self):
        source = AccountSession("tester@example.invalid", "tester", True, "dummy")
        self.assertEqual(source.source, "xray")
        self.assertFalse(source.proxy_locations)


class TestPremiumLoopback(unittest.TestCase):
    def setUp(self):
        self.bridge = PremiumBrowserBridge()
        self.received = []
        self.pair = self.bridge.start(self.received.append)

    def tearDown(self):
        self.bridge.stop()

    def send(self, *, origin=ORIGIN, code=None, payload=None):
        req = Request(
            "http://127.0.0.1:%d/premium-session" % self.pair.port,
            data=json.dumps(MOCK if payload is None else payload).encode(),
            headers={
                "Origin": origin,
                "Content-Type": "application/json",
                "X-OneTunnel-Pairing": self.pair.code if code is None else code,
            },
            method="POST",
        )
        with urlopen(req, timeout=3) as response:
            return response.status, json.load(response)

    def test_requires_extension_origin(self):
        with self.assertRaises(HTTPError) as e:
            self.send(origin="https://1vpn.org")
        self.assertEqual(e.exception.code, 403)
        self.assertEqual(self.received, [])

    def test_requires_pairing_secret(self):
        with self.assertRaises(HTTPError) as e:
            self.send(code="bad-code")
        self.assertEqual(e.exception.code, 403)
        self.assertEqual(self.received, [])

    def test_valid_single_use_delivery(self):
        status, reply = self.send()
        self.assertEqual(status, 200)
        self.assertTrue(reply["ok"])
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].username, MOCK["username"])

    def test_rejected_payload_does_not_consume_code(self):
        with self.assertRaises(HTTPError) as e:
            self.send(payload={**MOCK, "isPremium": False})
        self.assertEqual(e.exception.code, 422)
        self.assertEqual(self.received, [])
        self.assertEqual(self.send()[0], 200)

    def test_invalid_cors_origin_disallowed(self):
        req = Request(
            "http://127.0.0.1:%d/premium-session" % self.pair.port,
            method="OPTIONS",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        )
        with self.assertRaises(HTTPError) as e:
            urlopen(req, timeout=3)
        self.assertEqual(e.exception.code, 403)
