import unittest

from main import (
    build_historical_workday_profile,
    get_india_working_hours_profile,
    generate_ai_answer,
)


class HistoricalForecastTests(unittest.TestCase):
    def test_workday_profile_has_working_hours(self):
        profile = build_historical_workday_profile("Bengaluru Urban", 35, 60, month=4)
        self.assertGreater(len(profile), 0)
        self.assertIn("time", profile[0])
        self.assertIn("temperature_high", profile[0])
        self.assertIn("temperature_low", profile[0])

    def test_working_hours_profile_has_sequence(self):
        profile = get_india_working_hours_profile("Bengaluru Urban", 35, 60)
        self.assertGreater(len(profile), 5)
        self.assertEqual(profile[0]["time"], "08:00")

    def test_ai_answer_uses_basic_rules(self):
        answer = generate_ai_answer("What is the current heat risk?", "Bengaluru Urban", 35, 60)
        self.assertIn("risk", answer.lower())


if __name__ == "__main__":
    unittest.main()
