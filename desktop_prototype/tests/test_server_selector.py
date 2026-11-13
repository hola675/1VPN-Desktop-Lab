import unittest
from unittest.mock import patch

from proxycore import Upstream
from server_catalog import ServerEndpoint, snapshot_catalogue
from server_selector import (AutoSelector, ProbeResult, PREFERENCE_MARGIN_MS,
                             probe_endpoint)


class TestSelector(unittest.TestCase):
    def setUp(self):
        self.sg = ServerEndpoint("sgp", "free-singapore-https-1.cloudburstcdn.com")
        self.am = ServerEndpoint("ams", "free-amsterdam-https-1.cloudburstcdn.com")
        self.la = ServerEndpoint("lax", "free-los-angeles-https-1.cloudburstcdn.com")

    def selector(self, timings, region="auto"):
        def probe(endpoint, username, password, timeout):
            value = timings.get(endpoint.region)
            return ProbeResult(endpoint, True, value) if value else ProbeResult(endpoint, False, reason="TimeoutError")
        return AutoSelector((self.sg, self.am, self.la), "user", "secret", region=region, probe=probe)

    def test_singapore_wins_if_close_to_fastest(self):
        selector = self.selector({"sgp": 100, "ams": 80, "lax": 150})
        result = selector.scan()
        self.assertEqual(len(result), 3)
        self.assertEqual(selector.candidates()[0].host, self.sg.hostname)
        self.assertEqual(selector.summary()["rtt_ms"], 100)

    def test_fastest_wins_outside_margin(self):
        selector = self.selector({"sgp": 210, "ams": 75, "lax": 120})
        selector.scan()
        self.assertEqual(selector.candidates()[0].host, self.am.hostname)

    def test_fallback_after_failure(self):
        selector = self.selector({"sgp": 100, "ams": 80, "lax": 150})
        selector.scan()
        first = selector.candidates()[0]
        self.assertEqual(first.host, self.sg.hostname)
        selector.mark_failure(first, "timeout")
        self.assertEqual(selector.candidates()[0].host, self.am.hostname)
        self.assertEqual(selector.summary()["ok"], 2)
        self.assertNotIn(first.host, [s.host for s in selector.candidates()])

    def test_fixed_region_does_not_escape_to_other_region(self):
        selector = self.selector({"sgp": None, "ams": 10, "lax": 20}, region="sgp")
        selector.scan()
        self.assertTrue(all(c.host == self.sg.hostname for c in selector.candidates()))

    def test_no_fallback_to_direct_if_all_fail(self):
        selector = self.selector({})
        selector.scan()
        self.assertTrue(all(c.host for c in selector.candidates()))
        self.assertNotIn("direct", str(selector.candidates()))

    def test_reject_bad_region_and_empty_snapshot(self):
        with self.assertRaises(ValueError): AutoSelector(region="premium")
        with self.assertRaises(ValueError): AutoSelector(endpoints=())

    def test_set_catalogue_replaces_unlisted(self):
        selector = self.selector({"sgp": 100, "ams": 80, "lax": 150})
        selector.scan()
        selector.set_catalogue((self.sg,))
        self.assertEqual(len(selector.candidates()), 1)

    def test_credentials_are_kept_in_memory_not_in_logs(self):
        selector = self.selector({"sgp": 100, "ams": 80, "lax": 150})
        self.assertEqual(selector.candidates()[0].password, "secret")
        self.assertNotIn("secret", str(selector.summary()))

    def test_probe_failed_tcp_connection(self):
        with patch("server_selector.socket.create_connection", side_effect=TimeoutError()) as connection:
            result = probe_endpoint(self.sg, "user", "secret", timeout=.5)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "TimeoutError")
        self.assertIsNone(result.rtt_ms)

if __name__ == "__main__": unittest.main()
