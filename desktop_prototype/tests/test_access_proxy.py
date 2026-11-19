"""Tests for the fail-closed network access proxy hop."""
import base64
import socket
import unittest
from unittest.mock import patch

from access_proxy import AccessProxy, _connect_request, open_via_access_proxy
from server_catalog import ServerEndpoint
from server_selector import AutoSelector, ProbeResult


class FakeSocket:
    def __init__(self, response=b"HTTP/1.1 200 Connection Established\r\n\r\n"):
        self.response = response
        self.sent = b""
        self.closed = False
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value

    def sendall(self, data):
        self.sent += data

    def recv(self, _size):
        data, self.response = self.response, b""
        return data

    def close(self):
        self.closed = True


class AccessProxyTests(unittest.TestCase):
    def test_validation_and_secret_repr(self):
        proxy = AccessProxy("172.16.21.197", 3132, "user", "secret").validated()
        self.assertEqual(proxy.port, 3132)
        self.assertNotIn("secret", repr(proxy))
        for bad in (
            AccessProxy("", 3128),
            AccessProxy("bad host", 3128),
            AccessProxy("proxy.local", 0),
            AccessProxy("proxy.local", 70000),
            AccessProxy("proxy.local", 3128, "bad:user", "x"),
            AccessProxy("proxy.local", 3128, "user", "x\r\ny"),
        ):
            with self.subTest(proxy=repr(bad)):
                with self.assertRaises(ValueError):
                    bad.validated()

    def test_connect_request_has_basic_auth_but_no_target_credentials(self):
        proxy = AccessProxy("proxy.local", 3128, "alice", "p@ss")
        request = _connect_request(proxy, "vpn.example.org", 443)
        token = base64.b64encode(b"alice:p@ss")
        self.assertIn(b"CONNECT vpn.example.org:443 HTTP/1.1", request)
        self.assertIn(b"Proxy-Authorization: Basic " + token, request)
        self.assertNotIn(b"p@ss", request)

    def test_open_uses_only_access_proxy_address(self):
        sock = FakeSocket()
        with patch("access_proxy.socket.create_connection", return_value=sock) as connect:
            result = open_via_access_proxy(
                AccessProxy("172.16.21.197", 3132),
                "vpn.example.org",
                443,
                timeout=2,
            )
        self.assertIs(result, sock)
        connect.assert_called_once_with(("172.16.21.197", 3132), timeout=2)
        self.assertIn(b"CONNECT vpn.example.org:443", sock.sent)
        self.assertFalse(sock.closed)

    def test_407_is_auth_error_and_socket_is_closed(self):
        sock = FakeSocket(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
        with patch("access_proxy.socket.create_connection", return_value=sock):
            with self.assertRaisesRegex(PermissionError, "407"):
                open_via_access_proxy(
                    AccessProxy("proxy.local", 3128, "bad", "bad"),
                    "vpn.example.org",
                    443,
                )
        self.assertTrue(sock.closed)

    def test_non_200_never_falls_back_direct(self):
        sock = FakeSocket(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        with patch("access_proxy.socket.create_connection", return_value=sock) as connect:
            with self.assertRaisesRegex(ConnectionError, "403"):
                open_via_access_proxy(
                    AccessProxy("proxy.local", 3128),
                    "vpn.example.org",
                    443,
                )
        self.assertEqual(connect.call_count, 1)
        self.assertEqual(connect.call_args.args[0], ("proxy.local", 3128))


class SelectorAccessProxyTests(unittest.TestCase):
    def test_selector_passes_access_proxy_to_probe(self):
        endpoint = ServerEndpoint("sgp", "vpn.example.org", 443)
        access = AccessProxy("proxy.local", 3128)
        seen = []

        def probe(ep, username, password, timeout, access_proxy):
            seen.append((ep, access_proxy))
            return ProbeResult(ep, True, 25.0)

        selector = AutoSelector(
            endpoints=(endpoint,),
            username="u",
            password="p",
            access_proxy=access,
            probe=probe,
        )
        results = selector.scan(workers=1, timeout=.1)
        self.assertTrue(results[0].ok)
        self.assertEqual(seen[0][1], access.validated())


if __name__ == "__main__":
    unittest.main()
