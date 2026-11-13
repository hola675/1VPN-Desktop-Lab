"""Integración TLS local en memoria de test (sin conectarse a 1VPN o Internet).

Si openssl no está disponible, se omite únicamente la prueba TLS; la suite
principal sigue siendo stdlib pura y ejecutable en Windows.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from proxycore import ProxyRelay, Upstream, _recv_header


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL CLI no disponible para generar certificado efímero de prueba")
class TestTLSRelay(unittest.TestCase):
    def test_connect_through_verified_tls_proxy(self):
        with tempfile.TemporaryDirectory() as directory:
            cert = str(Path(directory) / "cert.pem")
            key = str(Path(directory) / "key.pem")
            subprocess.run([
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-days", "1", "-subj", "/CN=localhost",
                "-addext", "subjectAltName=DNS:localhost",
                "-keyout", key, "-out", cert,
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)

            tls_server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls_server_context.load_cert_chain(certfile=cert, keyfile=key)
            tls_client_context = ssl.create_default_context(cafile=cert)

            received = {}
            server_error = []
            listening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listening.bind(("127.0.0.1", 0))
            listening.listen(1)
            listening.settimeout(10)
            upstream_port = listening.getsockname()[1]

            def fake_upstream():
                try:
                    with listening:
                        sock, _ = listening.accept()
                        with sock, tls_server_context.wrap_socket(sock, server_side=True) as tls:
                            tls.settimeout(8)
                            header, unused = _recv_header(tls)
                            received["header"] = header
                            tls.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                            received["message"] = tls.recv(4)
                            tls.sendall(b"PONG")
                except Exception as error:
                    server_error.append(error)

            upstream_thread = threading.Thread(target=fake_upstream, daemon=True)
            upstream_thread.start()
            relay = ProxyRelay(Upstream("localhost", upstream_port, "testuser", "testpass"))
            with patch("proxycore.ssl.create_default_context", return_value=tls_client_context):
                port = relay.start(local_port=0)
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=8) as client:
                        client.settimeout(8)
                        client.sendall(b"CONNECT example.org:443 HTTP/1.1\r\nHost: example.org:443\r\n\r\n")
                        response, _ = _recv_header(client)
                        self.assertIn(b"200 Connection Established", response)
                        client.sendall(b"PING")
                        self.assertEqual(client.recv(4), b"PONG")
                finally:
                    relay.stop()
            upstream_thread.join(timeout=8)
            self.assertFalse(server_error, repr(server_error))
            self.assertIn(b"Proxy-Authorization: Basic dGVzdHVzZXI6dGVzdHBhc3M=", received["header"])
            self.assertEqual(received["message"], b"PING")


if __name__ == "__main__":
    unittest.main()
