import unittest

from zta.web import create_app


class _Accounts:
    def authenticate(self, _username, _password):
        return True

    def create(self, _username, _password):
        pass


class _Classifier:
    def classify(self, _frame):
        raise AssertionError("injected camera pipeline should own test inference")


class _Pipeline:
    def __init__(self):
        self.started = []
        self.stopped = []

    def start(self, key, owner):
        self.started.append((key, owner))

    def stop(self, key, owner):
        self.stopped.append((key, owner))

    def wait_for_update(self, _key, _owner, _version):
        return 1, {
            "phase": "stopped",
            "error": "",
            "status": "below_threshold",
            "sample_count": 75,
            "fake_count": 0,
            "fake_ratio": 0.0,
            "window_size": 75,
            "model_id": "test-model",
            "liveness": {
                "status": "live",
                "instruction": "Depth liveness challenge complete",
                "reason": "depth_candidate",
                "observation_count": 8,
                "live_observation_count": 8,
                "challenge_complete": True,
                "valid_depth_ratio": 0.95,
                "median_depth_m": 0.7,
                "relief_m": 0.025,
                "face_box": [10, 10, 50, 50],
                "analyzer_id": "test-depth",
            },
        }


class WebCaptureTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = _Pipeline()
        self.app = create_app(
            {"TESTING": True, "SECRET_KEY": "test-secret"},
            classifier=_Classifier(),
            accounts=_Accounts(),
            capture_pipeline=self.pipeline,
        )
        self.client = self.app.test_client()
        self.client.get("/")
        with self.client.session_transaction() as session:
            self.csrf = session["csrf"]
            session["username"] = "tester"
            session["capture_owner"] = "owner"

    def test_capture_uses_status_stream_and_has_no_frame_upload_route(self):
        headers = {"X-CSRF-Token": self.csrf}
        response = self.client.post("/api/captures", headers=headers)
        self.assertEqual(201, response.status_code)
        capture_id = response.get_json()["capture_id"]
        self.assertEqual([(capture_id, "owner")], self.pipeline.started)

        response = self.client.get(f"/api/captures/{capture_id}/events")
        self.assertEqual(200, response.status_code)
        self.assertIn(b'"phase": "stopped"', response.data)
        self.assertIn(b'"liveness": {', response.data)

        response = self.client.post(
            f"/api/captures/{capture_id}/frames", headers=headers,
        )
        self.assertEqual(404, response.status_code)

        response = self.client.delete(
            f"/api/captures/{capture_id}", headers=headers,
        )
        self.assertEqual(204, response.status_code)
        self.assertEqual([(capture_id, "owner")], self.pipeline.stopped)


if __name__ == "__main__":
    unittest.main()
