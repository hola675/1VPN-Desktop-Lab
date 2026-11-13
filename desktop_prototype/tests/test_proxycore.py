import base64
import unittest
from proxycore import Upstream, _inject_proxy_auth


class TestProxyCore(unittest.TestCase):
    def test_upstream_validation(self):
        self.assertEqual(Upstream("proxy.example.org", 443).validated().port, 443)
        with self.assertRaises(ValueError):
            Upstream("bad host", 443).validated()
        with self.assertRaises(ValueError):
            Upstream("proxy.example.org", 65536).validated()

    def test_authorization_replaces_client_auth(self):
        upstream = Upstream("proxy.example.org", 443, "user", "pass")
        request = b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\nProxy-Authorization: Basic OLD\r\n\r\n"
        output = _inject_proxy_auth(request, upstream)
        self.assertNotIn(b"OLD", output)
        self.assertIn(b"Proxy-Authorization: Basic " + base64.b64encode(b"user:pass"), output)
        self.assertTrue(output.endswith(b"\r\n\r\n"))

    def test_no_credentials_when_not_provided(self):
        output = _inject_proxy_auth(b"GET http://example.com/ HTTP/1.1\r\nHost: example.com\r\n\r\n", Upstream("proxy.example.org", 443))
        self.assertNotIn(b"Proxy-Authorization", output)

    def test_must_end_with_headers(self):
        with self.assertRaises(ValueError):
            _inject_proxy_auth(b"GET / HTTP/1.1\r\n", Upstream("proxy.example.org", 443))


if __name__ == "__main__":
    unittest.main()

class TestLocalListener(unittest.TestCase):
    def test_only_loopback_and_rejects_unsupported_methods(self):
        import socket
        from proxycore import ProxyRelay
        relay = ProxyRelay(Upstream("proxy.example.org", 443))
        try:
            port = relay.start()
            self.assertEqual(relay.server.server_address[0], "127.0.0.1")
            with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                client.sendall(b"BREW / HTTP/1.1\r\nHost: example.org\r\n\r\n")
                self.assertIn(b"405 Method Not Allowed", client.recv(1024))
        finally:
            relay.stop()
