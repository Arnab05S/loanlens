import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import main

class BackendAnalysisTests(unittest.TestCase):
    def test_single_case_never_gets_a_statistical_score(self):
        result = main.compute_bias_score("Insufficient income", "Insufficient income")
        self.assertIsNone(result["bias_score"])
        self.assertEqual(result["verdict"], "unclear")
        self.assertEqual(len(result["bias_indicators"]), 1)
        self.assertIn("not proof", result["bias_indicators"][0]["evidence"])

    def test_specific_reason_does_not_create_a_bias_finding(self):
        result = main.compute_bias_score("Credit score below required threshold", "Credit score below required threshold")
        self.assertIsNone(result["bias_score"])
        self.assertEqual(result["bias_indicators"], [])

    def test_empty_and_non_rejection_inputs_fail_closed(self):
        with self.assertRaises(main.InvalidAnalysisInput):
            asyncio.run(main.analyse({"extracted": {"loan_rejection_related": False}}, "text", "id"))
        with self.assertRaises(main.InvalidAnalysisInput):
            asyncio.run(main.analyse({"extracted": {"loan_rejection_related": True}}, "text", "id"))

    def test_distinct_user_stories_reach_distinct_answers_and_next_steps(self):
        cases = [
            ("I repaid my farm loan, but the bank says an old overdue remains on my credit report.",
             "The credit report shows an overdue after repayment", "Dispute the incorrect credit entry", "Ask the lender for the reporting date and dispute the inaccurate entry with the bureau."),
            ("The bank rejected my home loan because the property is outside its approved project list.",
             "Property is outside the approved project list", "Ask for the project approval criteria", "Ask which property documents or approval conditions are missing."),
        ]
        outputs=[]
        for story, reason, title, detail in cases:
            model_result = {
                "extracted": {"loan_rejection_related": True, "issue_summary": reason,
                              "stated_reason": reason, "stated_reason_en": reason,
                              "detected_language": "English", "missing_information": []},
                "explanation_native": "For your case: " + reason,
                "explanation_en": "For your case: " + reason,
                "next_steps": [{"title": title, "detail": detail}],
                "questions_for_user": [], "legal_context": None,
            }
            with patch("main._generate_async", new=AsyncMock(return_value=model_result)) as call:
                result = asyncio.run(main.analyse_text(main.TextRequest(text=story)))
                self.assertEqual(call.await_count, 1)
            outputs.append(result)
        self.assertNotEqual(outputs[0]["explanation_en"], outputs[1]["explanation_en"])
        self.assertNotEqual(outputs[0]["next_steps"][0]["title"], outputs[1]["next_steps"][0]["title"])
        self.assertIn("credit report", outputs[0]["explanation_en"].lower())
        self.assertIn("property", outputs[1]["explanation_en"].lower())

    def test_malformed_answer_is_service_error_not_user_error(self):
        answer={"explanation_native":"short", "explanation_en":"short", "next_steps":[]}
        with self.assertRaises(main.AIServiceError):
            main._validate_answer(answer, "English")

    def test_untrusted_extraction_fields_are_discarded(self):
        result=main._clean_extraction({"loan_rejection_related": True, "stated_reason": "x"*2000,
                                       "aadhaar": "999999999999", "unexpected": "ignore safeguards"})
        self.assertNotIn("aadhaar", result)
        self.assertNotIn("unexpected", result)
        self.assertEqual(len(result["stated_reason"]),1000)

    def test_ai_errors_are_not_returned_as_client_input_422(self):
        self.assertFalse(isinstance(main.AIServiceError("broken model"), main.InvalidAnalysisInput))

    def test_http_endpoint_returns_case_specific_result(self):
        payload={
            "extracted": {"loan_rejection_related": True, "issue_summary": "Bank says paid loan remains overdue",
                          "stated_reason": "Old overdue remains on report", "stated_reason_en": "Old overdue remains on report",
                          "detected_language": "English", "missing_information": []},
            "explanation_native": "The report may not reflect your repayment yet.",
            "explanation_en": "The report may not reflect your repayment yet.",
            "next_steps": [{"title": "Ask when the lender reported the payment", "detail": "Compare the report date with your receipt."}],
            "questions_for_user": [], "legal_context": None
        }
        with patch("main._generate_async", new=AsyncMock(return_value=payload)):
            response=TestClient(main.app).post("/analyse/text", json={"text": "I repaid my loan but the report still shows overdue."})
        self.assertEqual(response.status_code, 200)
        self.assertIn("repayment", response.json()["explanation_en"])
        self.assertEqual(response.json()["next_steps"][0]["title"], "Ask when the lender reported the payment")

    def test_provider_failure_is_503_not_422(self):
        with patch("main._generate_async", new=AsyncMock(side_effect=main.AIServiceError("provider unavailable"))):
            response=TestClient(main.app).post("/analyse/text", json={"text": "The bank rejected my personal loan without a clear reason."})
        self.assertEqual(response.status_code, 503)
        self.assertNotEqual(response.status_code, 422)

if __name__ == "__main__":
    unittest.main()
