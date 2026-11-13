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

    def test_rejects_crlf_or_colon_in_username(self):
        with self.assertRaises(ValueError):
            Upstream("proxy.example.org", 443, "evil:username", "pass").validated()
        with self.assertRaises(ValueError):
            Upstream("proxy.example.org", 443, "u\r\nBad: yes", "pass").validated()

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
            port = relay.start(local_port=0)
            self.assertEqual(relay.server.server_address[0], "127.0.0.1")
            with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                client.sendall(b"BREW / HTTP/1.1\r\nHost: example.org\r\n\r\n")
                self.assertIn(b"405 Method Not Allowed", client.recv(1024))
        finally:
            relay.stop()


class TestPortSelection(unittest.TestCase):
    def test_rejects_invalid_port_and_allows_fixed_local_port(self):
        from proxycore import ProxyRelay, Upstream
        import socket
        relay = ProxyRelay(Upstream("proxy.example.org", 443))
        with self.assertRaises(ValueError):
            relay.start(-1)
        with self.assertRaises(ValueError):
            relay.start(65536)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved:
            reserved.bind(("127.0.0.1", 0))
            reserved.listen()
            port = reserved.getsockname()[1]
            # El puerto ocupado no se pisa ni se selecciona silenciosamente otro.
            with self.assertRaises(OSError):
                relay.start(port)
        try:
            self.assertEqual(relay.start(port), port)
        finally:
            relay.stop()


class TestRemoteFailures(unittest.TestCase):
    """Distingue errores remotos, sin filtrar los destinos al registro local."""

    def test_connection_timeout_is_504_and_never_falls_back_to_direct(self):
        import socket
        from unittest.mock import patch
        from proxycore import ProxyRelay

        logs = []
        relay = ProxyRelay(Upstream("remote.example.org", 443), logs.append)
        port = relay.start(0)
        try:
            real_create_connection = socket.create_connection
            def fail_remote(address, timeout=None):
                if address[0] == "127.0.0.1":
                    return real_create_connection(address, timeout)
                raise TimeoutError("secret target")
            with patch("proxycore.socket.create_connection", side_effect=fail_remote):
                with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
                    client.settimeout(3)
                    client.sendall(b"CONNECT sensitive.example.org:7551 HTTP/1.1\r\nHost: sensitive.example.org:7551\r\n\r\n")
                    result = client.recv(1024)
            self.assertIn(b"504 Gateway Timeout", result)
            self.assertIn("puerto destino 7551", " ".join(logs))
            self.assertIn("conexión TCP al proxy remoto", " ".join(logs))
            self.assertNotIn("sensitive.example.org", " ".join(logs))
            self.assertNotIn("secret target", " ".join(logs))
        finally:
            relay.stop()

    def test_connection_error_is_502(self):
        import socket
        from unittest.mock import patch
        from proxycore import ProxyRelay

        relay = ProxyRelay(Upstream("remote.example.org", 443))
        port = relay.start(0)
        try:
            real_create_connection = socket.create_connection
            def fail_remote(address, timeout=None):
                if address[0] == "127.0.0.1":
                    return real_create_connection(address, timeout)
                raise ConnectionRefusedError()
            with patch("proxycore.socket.create_connection", side_effect=fail_remote):
                with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
                    client.settimeout(3)
                    client.sendall(b"CONNECT example.org:443 HTTP/1.1\r\nHost: example.org:443\r\n\r\n")
                    self.assertIn(b"502 Bad Gateway", client.recv(1024))
        finally:
            relay.stop()
