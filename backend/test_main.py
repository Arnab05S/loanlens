import unittest
import asyncio
from unittest.mock import patch
import main

class ReviewSignalTests(unittest.TestCase):
    def test_vague_reason_only_prompts_clarification(self):
        result = main.compute_bias_score("Insufficient income", "Insufficient income")
        self.assertIsNone(result["bias_score"])
        self.assertEqual(result["verdict"], "unclear")
        self.assertEqual(len(result["bias_indicators"]), 1)
        self.assertIn("not proof", result["bias_indicators"][0]["evidence"])

    def test_specific_reason_does_not_create_a_bias_finding(self):
        result = main.compute_bias_score("Credit score below required threshold", "Credit score below required threshold")
        self.assertIsNone(result["bias_score"])
        self.assertEqual(result["verdict"], "unclear")
        self.assertEqual(result["bias_indicators"], [])

    def test_no_demographic_attribute_scoring(self):
        with self.assertRaises(TypeError):
            main.compute_bias_score("Insufficient income", gender="female")

    def test_empty_extraction_fails_closed(self):
        with self.assertRaises(ValueError):
            main.analyse({"detected_language": "Hindi"}, "text", "test-id")

    @patch("main._generate")
    def test_analysis_uses_per_request_extraction_and_explanation(self, generate):
        generate.side_effect = [
            {"stated_reason": "Credit score below threshold", "stated_reason_en": "Credit score below threshold", "loan_amount": "₹50,000", "detected_language": "Hindi"},
            {"explanation_native": "बैंक ने क्रेडिट स्कोर का कारण दिया।", "explanation_en": "The bank cited the credit score."},
        ]
        result = asyncio.run(main.analyse_text(main.TextRequest(text="The bank rejected me because my credit score was below its threshold.")))
        self.assertEqual(result["extracted"]["stated_reason_en"], "Credit score below threshold")
        self.assertEqual(result["explanation_en"], "The bank cited the credit score.")
        self.assertIsNone(result["bias_score"])
        self.assertEqual(generate.call_count, 2)

if __name__ == "__main__":
    unittest.main()
