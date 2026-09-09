import importlib
import os
import unittest
from unittest.mock import patch


class LiveWeatherFallbackTest(unittest.TestCase):
    def test_weather_endpoint_works_without_tomorrow_key(self):
        original = os.environ.get("TOMORROW_API_KEY")
        os.environ.pop("TOMORROW_API_KEY", None)

        try:
            import main

            importlib.reload(main)
            from fastapi.testclient import TestClient

            client = TestClient(main.app)
            response = client.get("/weather/Bengaluru%20Urban")

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertIn("temperature", payload)
            self.assertIn("risk_level", payload)
            self.assertIn("location", payload)
            self.assertGreater(payload["temperature"], -50)
        finally:
            if original is not None:
                os.environ["TOMORROW_API_KEY"] = original
            else:
                os.environ.pop("TOMORROW_API_KEY", None)
            if "main" in globals():
                import main as module
                importlib.reload(module)


if __name__ == "__main__":
    unittest.main()
