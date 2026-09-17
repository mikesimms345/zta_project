import unittest
from zta.domain import Label, Prediction, Status, ModelUnavailable
from zta.policy import EvidencePolicy
from zta.service import VerificationService, SessionNotFound, CapacityExceeded


class Classifier:
    def __init__(self):
        self.label = Label.FAKE
        self.model_id = 'test-model'
        self.fail = False

    def classify(self, frame):
        if self.fail:
            raise ModelUnavailable('offline')
        return Prediction(self.label, self.model_id)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.model = Classifier()
        self.now = 0
        self.service = VerificationService(self.model, EvidencePolicy(3, 2/3),
                                           clock=lambda: self.now, ttl=5, max_sessions=2)
        self.key = self.service.start('alice')

    def submit(self):
        return self.service.submit(self.key, 'alice', b'frame')

    def test_warmup_threshold_and_rolling_window(self):
        self.assertEqual(self.submit().status, Status.COLLECTING)
        self.assertEqual(self.submit().status, Status.COLLECTING)
        self.model.label = Label.REAL
        self.assertEqual(self.submit().status, Status.FLAGGED)
        result = self.submit()
        self.assertEqual(result.status, Status.BELOW_THRESHOLD)
        self.assertEqual(result.fake_count, 1)

    def test_ownership_expiry_and_capacity(self):
        with self.assertRaises(SessionNotFound):
            self.service.submit(self.key, 'bob', b'frame')
        self.service.start('bob')
        with self.assertRaises(CapacityExceeded):
            self.service.start('carol')
        self.now = 5
        with self.assertRaises(SessionNotFound):
            self.submit()
        self.service.start('carol')

    def test_model_failure_does_not_add_evidence(self):
        self.submit()
        self.model.fail = True
        with self.assertRaises(ModelUnavailable):
            self.submit()
        self.model.fail = False
        self.assertEqual(self.submit().sample_count, 2)

    def test_model_upgrade_resets_window(self):
        self.submit()
        self.model.model_id = 'replacement'
        self.assertEqual(self.submit().sample_count, 1)

    def test_stop_removes_capture(self):
        self.service.stop(self.key, 'alice')
        with self.assertRaises(SessionNotFound):
            self.submit()

    def test_invalid_configuration(self):
        for size, threshold in [(0, .7), (3, 0), (3, float('nan'))]:
            with self.assertRaises(ValueError):
                EvidencePolicy(size, threshold)


if __name__ == '__main__':
    unittest.main()
