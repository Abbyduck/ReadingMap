"""The historical startup path must enforce the current backend permissions."""
from asgiref.sync import async_to_sync
from asgiref.testing import ApplicationCommunicator
from django.test import SimpleTestCase


class HistoricalEntryPointTests(SimpleTestCase):
    async def request_status(self, path):
        from app.main import app
        communicator = ApplicationCommunicator(app, {
            "type": "http", "http_version": "1.1", "method": "GET",
            "path": path, "raw_path": path.encode(), "query_string": b"",
            "headers": [(b"host", b"testserver")], "scheme": "http",
            "server": ("testserver", 80), "client": ("127.0.0.1", 10000),
        })
        await communicator.send_input({"type": "http.request", "body": b"", "more_body": False})
        response = await communicator.receive_output()
        while True:
            body = await communicator.receive_output()
            if not body.get("more_body", False):
                break
        await communicator.wait()
        return response["status"]

    def test_legacy_path_denies_anonymous_child_reads(self):
        self.assertEqual(async_to_sync(self.request_status)("/api/children"), 403)

    def test_legacy_path_denies_anonymous_review_reads(self):
        self.assertEqual(async_to_sync(self.request_status)("/api/review/batches"), 403)
