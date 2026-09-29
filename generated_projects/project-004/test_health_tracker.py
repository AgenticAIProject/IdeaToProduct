import unittest, json
class MockStorage:
    def __init__(self): self.data = {}
    def getItem(self, k): return self.data.get(k)
    def setItem(self, k, v): self.data[k] = v
class TestHealthTracker(unittest.TestCase):
    def setUp(self):
        self.storage = MockStorage()
        self.today = '2023-10-27'
    def test_save_valid_data(self):
        data = {'steps': 1000, 'waterIntakeMl': 500}
        self.storage.setItem(self.today, json.dumps(data))
        self.assertEqual(json.loads(self.storage.getItem(self.today))['steps'], 1000)
    def test_save_negative_data(self):
        steps = -10
        self.assertTrue(steps < 0)
    def test_load_existing_data(self):
        self.storage.setItem(self.today, json.dumps({'steps': 500, 'waterIntakeMl': 200}))
        self.assertIsNotNone(self.storage.getItem(self.today))
if __name__ == '__main__': unittest.main()