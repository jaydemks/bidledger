import importlib.util
import pathlib
import unittest
from unittest import mock
import urllib.error


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bidledger_sync", ROOT / "scripts" / "sync.py")
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"notices": []}'


class PostRetryTests(unittest.TestCase):
    @mock.patch.object(sync.time, "sleep")
    @mock.patch.object(sync.urllib.request, "urlopen")
    def test_retries_transient_403(self, urlopen, sleep):
        urlopen.side_effect = [
            urllib.error.HTTPError(sync.API, 403, "Forbidden", {}, None),
            Response(),
        ]

        self.assertEqual(sync.post({"query": "test"}), {"notices": []})
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(3)

    @mock.patch.object(sync.time, "sleep")
    @mock.patch.object(sync.urllib.request, "urlopen")
    def test_honours_numeric_retry_after(self, urlopen, sleep):
        urlopen.side_effect = [
            urllib.error.HTTPError(
                sync.API, 429, "Too Many Requests", {"Retry-After": "17"}, None
            ),
            Response(),
        ]

        sync.post({"query": "test"})
        sleep.assert_called_once_with(17)

    @mock.patch.object(sync.time, "sleep")
    @mock.patch.object(sync.urllib.request, "urlopen")
    def test_does_not_retry_permanent_client_error(self, urlopen, sleep):
        error = urllib.error.HTTPError(sync.API, 400, "Bad Request", {}, None)
        urlopen.side_effect = error

        with self.assertRaises(urllib.error.HTTPError):
            sync.post({"query": "test"})
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
