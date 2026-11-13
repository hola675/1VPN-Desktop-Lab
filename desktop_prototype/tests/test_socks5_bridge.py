"""Prueba local SOCKS5 -> HTTP CONNECT; sin servidores externos."""
import socket
import socketserver
import struct
import threading
import unittest

from socks5_bridge import Socks5Bridge


class MockHTTP(socketserver.BaseRequestHandler):
    def handle(self):
        data = b""
        while b"\r\n\r\n" not in data:
            data += self.request.recv(4096)
        self.server.requests.append(data.split(b"\r\n", 1)[0])
        if self.server.reject:
            self.request.sendall(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
        else:
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if self.request.recv(4) == b"PING":
                self.request.sendall(b"PONG")


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class TestSocks5(unittest.TestCase):
    def setUp(self):
        self.server = Server(("127.0.0.1", 0), MockHTTP)
        self.server.requests = []
        self.server.reject = False
        self.t = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.t.start()
        self.bridge = Socks5Bridge(self.server.server_address[1])
        self.port = self.bridge.start(0)

    def tearDown(self):
        self.bridge.stop()
        self.server.shutdown()
        self.server.server_close()
        self.t.join(timeout=2)

    def open(self):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
        sock.settimeout(2)
        sock.sendall(b"\x05\x01\x00")
        self.assertEqual(sock.recv(2), b"\x05\x00")
        return sock

    def test_connect_domain_and_data(self):
        with self.open() as sock:
            sock.sendall(b"\x05\x01\x00\x03\x0bexample.org" + struct.pack("!H", 443))
            self.assertEqual(sock.recv(10)[:2], b"\x05\x00")
            sock.sendall(b"PING")
            self.assertEqual(sock.recv(4), b"PONG")
        self.assertEqual(self.server.requests, [b"CONNECT example.org:443 HTTP/1.1"])

    def test_ipv4(self):
        with self.open() as sock:
            sock.sendall(b"\x05\x01\x00\x01" + socket.inet_aton("203.0.113.9") + struct.pack("!H", 8443))
            self.assertEqual(sock.recv(10)[:2], b"\x05\x00")
            sock.sendall(b"PING")
            self.assertEqual(sock.recv(4), b"PONG")
        self.assertEqual(self.server.requests, [b"CONNECT 203.0.113.9:8443 HTTP/1.1"])

    def test_udp_refused(self):
        with self.open() as sock:
            sock.sendall(b"\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00")
            self.assertEqual(sock.recv(10)[:2], b"\x05\x07")

    def test_auth_required_rejected(self):
        self.server.reject = True
        with self.open() as sock:
            sock.sendall(b"\x05\x01\x00\x03\x0bexample.org" + struct.pack("!H", 443))
            self.assertEqual(sock.recv(10)[:2], b"\x05\x05")

    def test_listen_only_loopback(self):
        self.assertEqual(self.bridge.server.server_address[0], "127.0.0.1")
        with self.assertRaises(ValueError):
            Socks5Bridge(0)


if __name__ == "__main__":
    unittest.main()
