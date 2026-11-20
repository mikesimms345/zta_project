"""HTTP lifecycle and media-session cancellation regression coverage."""
from dataclasses import asdict
from importlib import import_module
import json
from pathlib import Path
import tempfile
from threading import Event, Thread
import unittest

from zta.accounts import LocalAccounts
from zta.liveness.rppg import RppgEvidence, RppgStatus
from zta.web import create_app


domain = import_module('zta.deepfake-detection.domain')
service_module = import_module('zta.deepfake-detection.cnn-service')


class Classifier:
    def classify(self, frame):
        return domain.Prediction(domain.Label.REAL, 'test-model')


class Capture:
    def __init__(self):
        self.owner = None
        self.key = None
        self.stops = 0

    def start(self, key, owner):
        self.key, self.owner = key, owner

    def stop(self, key, owner):
        if owner != self.owner or key != self.key:
            raise LookupError('Invalid capture')
        self.stops += 1

    def wait_for_update(self, key, owner, version):
        assert key == self.key and owner == self.owner
        return 1, {'phase': 'completed', 'error': '', 'rppg': asdict(RppgEvidence(
            RppgStatus.INCONCLUSIVE, 'insufficient_capture', 'Start another check'))}


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        accounts = LocalAccounts(str(Path(self.temp.name) / 'accounts.db'))
        accounts.create('researcher', 'test-password-123')
        self.capture = Capture()
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only'},
                              accounts=accounts, classifier=Classifier(), capture_pipeline=self.capture)
        self.client = self.app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as session:
            token = session['csrf']
        result = self.client.post('/api/login', json={'username': 'researcher', 'password': 'test-password-123'},
                                  headers={'X-CSRF-Token': token})
        self.assertEqual(result.status_code, 200)
        with self.client.session_transaction() as session:
            self.headers = {'X-CSRF-Token': session['csrf']}

    def test_completed_sse_closes_and_only_transmits_summary(self):
        response = self.client.post('/api/captures', headers=self.headers)
        self.assertEqual(response.status_code, 201)
        key = response.json['capture_id']
        response = self.client.get(f'/api/captures/{key}/events')
        chunks = list(response.response)
        self.assertEqual(len(chunks), 1)
        state = json.loads(chunks[0].decode().removeprefix('data: ').strip())
        self.assertEqual(state['phase'], 'completed')
        self.assertIsNone(state['rppg']['bpm'])
        self.assertNotIn('samples', state['rppg'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.delete(f'/api/captures/{key}', headers=self.headers).status_code, 204)
        self.assertEqual(self.capture.stops, 1)

    def test_csrf_and_signed_in_session_still_required(self):
        self.assertEqual(self.client.post('/api/captures').status_code, 403)
        other = self.app.test_client()
        other.get('/')
        with other.session_transaction() as session:
            headers = {'X-CSRF-Token': session['csrf']}
        self.assertEqual(other.post('/api/captures', headers=headers).status_code, 401)


class SessionTests(unittest.TestCase):
    def test_expired_inflight_prediction_is_not_recorded(self):
        stamp = [0.0]
        class ExpiringClassifier:
            def classify(self, frame):
                stamp[0] = 2.0
                return domain.Prediction(domain.Label.REAL, 'test-model')
        service = service_module.VerificationService(ExpiringClassifier(),
                                                     clock=lambda: stamp[0], ttl=1)
        key = service.start('owner')
        with self.assertRaises(service_module.SessionNotFound):
            service.submit(key, 'owner', None)
        self.assertEqual(len(service._sessions), 0)

    def test_stop_during_inference_discards_late_prediction(self):
        entered, release = Event(), Event()
        class SlowClassifier:
            def classify(self, frame):
                entered.set()
                release.wait(3)
                return domain.Prediction(domain.Label.REAL, 'test-model')
        service = service_module.VerificationService(SlowClassifier())
        key = service.start('owner')
        failures = []
        def submit():
            try:
                service.submit(key, 'owner', None)
            except service_module.SessionNotFound:
                failures.append('discarded')
        worker = Thread(target=submit)
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            service.stop(key, 'owner')  # Must finish while classifier is still waiting.
            self.assertFalse(release.is_set())
        finally:
            release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, ['discarded'])


if __name__ == '__main__':
    unittest.main()
