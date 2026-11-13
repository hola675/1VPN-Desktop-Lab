"""Fallback CONNECT verificado de extremo a extremo con dos proxies TLS locales.

No realiza conexiones a proveedores externos ni transmite credenciales de 1VPN.
"""
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
from server_catalog import ServerEndpoint
from server_selector import AutoSelector, ProbeResult


@unittest.skipUnless(shutil.which("openssl"), "Se necesita openssl CLI para certificados efímeros")
class TestAutoFailoverTLS(unittest.TestCase):
    def test_rejected_upstream_is_retried_and_data_reaches_second_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            cert = str(Path(tmp) / "cert.pem")
            key = str(Path(tmp) / "key.pem")
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                            "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
                            "-keyout", key, "-out", cert], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_ctx.load_cert_chain(cert, key)
            client_ctx = ssl.create_default_context(cafile=cert)
            listeners = []
            for _ in range(2):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.bind(("127.0.0.1", 0))
                sock.listen(1)
                sock.settimeout(8)
                listeners.append(sock)
            ports = [sock.getsockname()[1] for sock in listeners]
            seen = []
            failures = []

            def serve(index):
                try:
                    with listeners[index] as listener:
                        conn, _ = listener.accept()
                        with conn, server_ctx.wrap_socket(conn, server_side=True) as remote:
                            remote.settimeout(8)
                            header, _ = _recv_header(remote)
                            seen.append((index, header))
                            if index == 0:
                                remote.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                            else:
                                remote.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                                if remote.recv(4) == b"PING":
                                    remote.sendall(b"PONG")
                except Exception as exc:
                    failures.append(exc)

            threads = [threading.Thread(target=serve, args=(i,), daemon=True) for i in range(2)]
            for thread in threads: thread.start()
            sg = ServerEndpoint("sgp", "localhost", ports[0])
            am = ServerEndpoint("ams", "localhost", ports[1])
            selector = AutoSelector((sg, am), username="user", password="pass")
            logs = []
            relay = ProxyRelay(Upstream("localhost", ports[0], "user", "pass"), logs.append, selector=selector)
            with patch("proxycore.ssl.create_default_context", return_value=client_ctx):
                port = relay.start()
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=8) as client:
                        client.settimeout(8)
                        client.sendall(b"CONNECT example.org:443 HTTP/1.1\r\nHost: example.org:443\r\n\r\n")
                        answer, _ = _recv_header(client)
                        self.assertTrue(answer.startswith(b"HTTP/1.1 200"), answer)
                        client.sendall(b"PING")
                        self.assertEqual(client.recv(4), b"PONG")
                finally:
                    relay.stop()
            for thread in threads: thread.join(timeout=8)
            self.assertEqual(failures, [])
            self.assertEqual([item[0] for item in seen], [0, 1])
            self.assertIn("CONNECT remoto rechazado: HTTP 502", " ".join(logs))
            self.assertEqual(selector.candidates()[0].port, ports[1])


if __name__ == "__main__": unittest.main()
