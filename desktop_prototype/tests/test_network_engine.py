"""Motor HTTP + SOCKS5 integrado: escucha local y rollback."""
import socket
import unittest
from unittest import mock

from network_engine import NetworkEngine
from proxycore import Upstream


class TestIntegratedEngine(unittest.TestCase):
    def test_both_listeners_and_safe_stop(self):
        engine = NetworkEngine()
        try:
            endpoints = engine.start(Upstream("proxy.example.org", 443), 0, 0)
            self.assertTrue(engine.active)
            self.assertNotEqual(endpoints.http_port, endpoints.socks5_port)
            for port in (endpoints.http_port, endpoints.socks5_port):
                with socket.create_connection(("127.0.0.1", port), timeout=2):
                    pass
            self.assertEqual(engine.http.server.server_address[0], "127.0.0.1")
            self.assertEqual(engine.socks.server.server_address[0], "127.0.0.1")
        finally:
            engine.stop()
        self.assertFalse(engine.active)
        engine.stop()

    def test_duplicate_ports_rejected(self):
        with self.assertRaises(ValueError):
            NetworkEngine().start(Upstream("proxy.example.org", 443), 5666, 5666)

    def test_rollback_when_socks_port_is_busy(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            engine = NetworkEngine()
            with self.assertRaises(OSError):
                engine.start(Upstream("proxy.example.org", 443), 0, occupied.getsockname()[1])
            self.assertFalse(engine.active)
            self.assertIsNone(engine.http)
            engine.stop()
