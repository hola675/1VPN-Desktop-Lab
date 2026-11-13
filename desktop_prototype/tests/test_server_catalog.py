"""Catálogo oficial: solamente servidores Free HTTPS/443 admitidos."""
import json
from io import BytesIO
import unittest
from unittest.mock import patch

from server_catalog import (API_URL, parse_free_catalogue, refresh_catalogue,
                            snapshot_catalogue, TRUSTED_SUFFIXES)


class TestCatalogue(unittest.TestCase):
    def test_regions_and_snapshot(self):
        servers = snapshot_catalogue()
        self.assertEqual({e.region for e in servers}, {"sgp", "ams", "lax"})
        self.assertEqual(len(servers), 16)
        self.assertTrue(all(e.port == 443 for e in servers))

    def test_rejects_premium_arbitrary_hosts_and_ports(self):
        doc = {
            "sgp": {"hosts": [{"hostname": "free-singapore-https-1.cloudburstcdn.com", "port": 443},
                              {"hostname": "malicious.example.com", "port": 443},
                              {"hostname": "host.cloudburstcdn.com", "port": 8080}]},
            "ams": {"isPremium": True, "hosts": [{"hostname": "free-amsterdam-https-1.cloudburstcdn.com", "port": 443}]},
            "lax": {"hosts": [{"hostname": "bad..host.cloudflingcdn.com", "port": 443}]},
        }
        parsed = parse_free_catalogue(doc)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].region, "sgp")

    def test_rejects_empty_or_untrusted_catalogue(self):
        for bad in ({}, [], {"sgp": {"hosts": [{"hostname": "evil.org", "port": 443}]}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_free_catalogue(bad)

    def test_deduplicates(self):
        host = {"hostname": "free-singapore-https-1.cloudburstcdn.com", "port": 443}
        parsed = parse_free_catalogue({"sgp": {"hosts": [host, host]}})
        self.assertEqual(len(parsed), 1)

    def test_refresh_sends_no_auth_credentials(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size):
                return json.dumps({"sgp": {"hosts": [{"hostname": "free-singapore-https-1.cloudburstcdn.com", "port": 443}]}}).encode()
        with patch("server_catalog.urllib.request.urlopen", return_value=Response()) as request:
            parsed = refresh_catalogue(timeout=2)
            self.assertEqual(len(parsed), 1)
            req = request.call_args.args[0]
            self.assertEqual(req.full_url, API_URL)
            self.assertFalse(any("authorization" in key.lower() for key in req.headers))

    def test_deny_big_catalogue(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size): return b"!" * size
        with patch("server_catalog.urllib.request.urlopen", return_value=Response()):
            with self.assertRaises(ValueError): refresh_catalogue()
