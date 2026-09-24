import tempfile
from pathlib import Path
import unittest
from zta.domain import Label, Prediction, ModelUnavailable
from zta.web import create_app


class Model:
    fail = False
    model_id = 'test-only'
    def classify(self, image):
        if self.fail:
            raise ModelUnavailable('offline')
        return Prediction(Label.REAL, self.model_id)


class WebTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.model = Model()
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-secret',
                               'DATABASE': str(Path(self.directory.name) / 'accounts.db'),
                               'WINDOW_SIZE': 2}, classifier=self.model)
        self.app.extensions['accounts'].create('alice', 'long-test-password')
        self.client = self.app.test_client()
        self.client.get('/')

    def headers(self, client=None):
        with (client or self.client).session_transaction() as session:
            return {'X-CSRF-Token': session['csrf']}

    def login(self, client=None):
        client = client or self.client
        client.get('/')
        return client.post('/api/login', headers=self.headers(client),
                           json={'username': 'alice', 'password': 'long-test-password'})

    def start(self):
        self.login()
        return self.client.post('/api/captures', headers=self.headers()).json['capture_id']

    def test_authentication_and_csrf(self):
        self.assertEqual(self.client.post('/api/captures').status_code, 403)
        self.assertEqual(self.client.post('/api/captures', headers=self.headers()).status_code, 401)
        self.assertEqual(self.client.post('/api/login', headers=self.headers(),
                                         json={'username': 'alice', 'password': 'wrong'}).status_code, 401)
        self.assertEqual(self.login().status_code, 200)

    def test_capture_isolation_and_logout(self):
        key = self.start()
        other = self.app.test_client()
        self.login(other)
        response = other.post(f'/api/captures/{key}/frames', headers=self.headers(other),
                              data=b'frame', content_type='image/jpeg')
        self.assertEqual(response.status_code, 404)
        response = self.client.post(f'/api/captures/{key}/frames', headers=self.headers(),
                                    data=b'frame', content_type='image/jpeg')
        self.assertEqual(response.json['status'], 'collecting')
        self.assertNotIn('authorized', response.json)
        self.assertEqual(self.client.post('/api/logout', headers=self.headers()).status_code, 204)
        self.client.get('/')
        self.assertEqual(self.client.post('/api/captures', headers=self.headers()).status_code, 401)

    def test_validation_and_model_failure(self):
        key = self.start()
        url = f'/api/captures/{key}/frames'
        self.assertEqual(self.client.post(url, headers=self.headers(), data=b'x').status_code, 415)
        self.assertEqual(self.client.post(url, headers=self.headers(), data=b'',
                                         content_type='image/jpeg').status_code, 400)
        self.assertEqual(self.client.post(url, headers=self.headers(), data=b'x' * (512*1024+1),
                                         content_type='image/jpeg').status_code, 413)
        self.model.fail = True
        self.assertEqual(self.client.post(url, headers=self.headers(), data=b'x',
                                         content_type='image/jpeg').status_code, 503)

    def test_restarting_capture_resets_evidence(self):
        key = self.start()
        def frame(key):
            return self.client.post(f'/api/captures/{key}/frames', headers=self.headers(),
                                    data=b'frame', content_type='image/jpeg')
        self.assertEqual(frame(key).json['sample_count'], 1)
        self.assertEqual(frame(key).json['sample_count'], 2)
        response = self.client.post('/api/captures', headers=self.headers())
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('model', response.json)
        new_key = response.json['capture_id']
        self.assertEqual(frame(key).status_code, 404)
        result = frame(new_key).json
        self.assertEqual(result['model_id'], 'test-only')
        self.assertEqual(result['sample_count'], 1)
        self.assertEqual(result['status'], 'collecting')

    def test_model_selection_rejected_without_deleting_capture(self):
        key = self.start()
        for model in ('cnn', 'other', None, [], {}):
            response = self.client.post('/api/captures', headers=self.headers(), json={'model': model})
            self.assertEqual(response.status_code, 400)
        response = self.client.post(f'/api/captures/{key}/frames', headers=self.headers(),
                                    data=b'frame', content_type='image/jpeg')
        self.assertEqual(response.status_code, 200)

    def test_signed_in_page_has_capture_controls_without_model_selector(self):
        self.login()
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('id="start"', html)
        self.assertIn('id="stop"', html)
        self.assertNotIn('model-selector', html)
        self.assertNotIn('name="model"', html)


if __name__ == '__main__':
    unittest.main()
