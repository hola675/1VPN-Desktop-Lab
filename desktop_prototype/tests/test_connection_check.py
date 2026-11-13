"""Pruebas del comprobador: sin abrir conexiones reales a Internet."""
import json
import unittest
from unittest.mock import patch

from connection_check import probe_exit_ip


class FakeResponse:
    status = 200

    def read(self, size):
        return json.dumps({"ip": "198.51.100.8"}).encode("utf-8")


class FakeConn:
    last = None
    def __init__(self, *args, **kwargs):
        FakeConn.last = self
        self.host, self.port = args[:2]
        self.tunnel = None
        self.request_args = None
        self.closed = False

    def set_tunnel(self, host, port):
        self.tunnel = (host, port)

    def request(self, *args, **kwargs):
        self.request_args = (args, kwargs)

    def getresponse(self):
        return FakeResponse()

    def close(self):
        self.closed = True


class TestConnectionCheck(unittest.TestCase):
    def test_validated_port_and_no_network(self):
        with self.assertRaises(ValueError):
            probe_exit_ip(0)
        with self.assertRaises(ValueError):
            probe_exit_ip(65536)

    def test_only_loopback_and_explicit_connect(self):
        with patch("connection_check.http.client.HTTPSConnection", FakeConn):
            result = probe_exit_ip(8899)
            self.assertEqual(result, "198.51.100.8")
            self.assertEqual(FakeConn.last.host, "127.0.0.1")
            self.assertEqual(FakeConn.last.port, 8899)
            self.assertEqual(FakeConn.last.tunnel, ("api.ipify.org", 443))
            self.assertTrue(FakeConn.last.closed)
            self.assertEqual(FakeConn.last.request_args[0][0], "GET")


if __name__ == "__main__":
    unittest.main()
