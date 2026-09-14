"""Offline runtime regressions; no external database or camera is contacted."""
import os
from pathlib import Path
import tempfile
import unittest

# Override any developer .env for this isolated test process.
os.environ.update(FLASK_ENV='testing', SECRET_KEY='runtime-test-only', DATABASE_URL='',
                  DB_USER='', DB_HOST='', MODEL_PATH='models/sign_language_model.h5')
import config
import app as application
import cnn_model
import numpy as np


class RuntimeTests(unittest.TestCase):
    def test_configuration_and_paths(self):
        cfg = config.get_config()
        self.assertEqual(cfg.SECRET_KEY, 'runtime-test-only')
        self.assertFalse(cfg.DATABASE_URL)
        self.assertEqual(Path(cfg.MODEL_PATH).parent, Path(__file__).resolve().parent / 'models')
        self.assertTrue(Path(cfg.MODEL_PATH).is_file())

    def test_public_routes_and_auth(self):
        client = application.app.test_client()
        for path in ['/', '/about', '/login', '/register']:
            self.assertEqual(client.get(path).status_code, 200, path)
        self.assertEqual(client.get('/dashboard').status_code, 302)
        self.assertEqual(client.post('/api/predict', json={}).status_code, 401)

    def test_absent_training_script_is_not_reported_as_started(self):
        client = application.app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 1
        result = client.post('/api/admin/start_training')
        self.assertEqual(result.status_code, 503)
        self.assertFalse(result.get_json()['success'])

    def test_prediction_buffer(self):
        buffer = cnn_model.PredictionBuffer()
        self.assertFalse(buffer.get_stable()['stable'])
        for _ in range(10):
            buffer.add('A', 90)
        self.assertTrue(buffer.get_stable()['stable'])
        buffer.reset()
        self.assertFalse(buffer.get_stable()['stable'])

    def test_trained_weights_load_and_execute(self):
        self.assertFalse(cnn_model.is_demo_mode(), 'Real weights failed to load; demo is not a passing inference test.')
        model = cnn_model.get_model()
        self.assertIsNotNone(model)
        shape = tuple(int(size) for size in model.input_shape[1:])
        # A zero tensor checks tensor compatibility only, not recognition accuracy.
        scores = cnn_model._run_model(np.zeros((1, *shape), dtype=np.float32))
        self.assertEqual(scores.shape, (1, 26))
        self.assertTrue(np.isfinite(scores).all())


if __name__ == '__main__':
    unittest.main()
