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


    def test_service_area_reason_and_missing_review_details_create_qualitative_flags(self):
        result = main.compute_bias_score(
            "Village outside bank branch service area", "Village outside bank branch service area",
            missing_information=["The notice does not give a policy clause or review contact."],
            source_text="The letter says the village is outside the branch service area and gives no policy clause or review contact."
        )
        self.assertIsNone(result["bias_score"])
        labels = {item["label"] for item in result["bias_indicators"]}
        self.assertIn("Reason is too general to verify", labels)
        self.assertIn("Decision basis or review route is missing", labels)
        self.assertTrue(all(item["score"] is None for item in result["bias_indicators"]))
        self.assertEqual(result["verdict"], "unclear")

    def test_exact_geography_community_and_opaque_scoring_case_gets_review_flags_not_a_probability(self):
        reason = ("Negative Geography / Non-Serviceable Pin-Code Cluster and "
                  "Internal Community & Residential Profile Stability Norms")
        source = (reason + ". The institution is not obligated to disclose granular scoring parameters.")
        result = main.compute_bias_score(reason, reason, source_text=source)
        self.assertIsNone(result["bias_score"])
        labels = {item["label"] for item in result["bias_indicators"]}
        self.assertIn("High-priority review flag: geography/serviceability criterion", labels)
        self.assertIn("High-priority review flag: undefined community/residential criterion", labels)
        self.assertIn("Request the basis behind the stated reasons", labels)
        self.assertTrue(all(item["score"] is None for item in result["bias_indicators"]))
        self.assertEqual(result["verdict"], "unclear")
        opaque = next(item for item in result["bias_indicators"] if item["label"] == "Request the basis behind the stated reasons")
        self.assertIn("does not establish an RBI violation", opaque["evidence"])

    def test_explicit_personal_characteristic_link_is_flagged_without_probability(self):
        reason = "Application rejected because the applicant is Muslim."
        result = main.compute_bias_score(reason, reason)
        self.assertIsNone(result["bias_score"])
        self.assertIn("Stated reason links the decision to a personal characteristic",
                      {item["label"] for item in result["bias_indicators"]})
        self.assertTrue(all(item["score"] is None for item in result["bias_indicators"]))

    def test_demographic_context_alone_is_not_a_review_signal(self):
        reason = "Credit score below the stated threshold; applicant is a woman from a rural district"
        result = main.compute_bias_score(reason, reason)
        self.assertIsNone(result["bias_score"])
        self.assertEqual(result["bias_indicators"], [])

    def test_personal_characteristic_unlinked_to_decision_is_not_flagged(self):
        reason = "Although I am a woman, my application was declined due to a low credit score."
        result = main.compute_bias_score(reason, reason)
        self.assertIsNone(result["bias_score"])
        self.assertEqual(result["bias_indicators"], [])

    def test_negated_personal_characteristic_link_is_not_flagged(self):
        reason = "The bank says it did not reject my application because I am Muslim."
        result = main.compute_bias_score(reason, reason)
        self.assertIsNone(result["bias_score"])
        self.assertEqual(result["bias_indicators"], [])

    def test_phrase_variant_is_flagged_only_as_a_clarification_request(self):
        reason = "Our district is outside the bank's service area"
        result = main.compute_bias_score(reason, reason)
        self.assertIsNone(result["bias_score"])
        self.assertIn("Reason is too general to verify", {item["label"] for item in result["bias_indicators"]})
        self.assertNotIn("unfair", result["bias_indicators"][0]["label"].lower())

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

    def test_http_endpoint_flags_missing_policy_detail_from_original_text(self):
        payload = {
            "extracted": {"loan_rejection_related": True, "issue_summary": "Service area restriction",
                          "stated_reason": "District outside bank branch service area",
                          "stated_reason_en": "District outside bank branch service area",
                          "detected_language": "English", "missing_information": []},
            "explanation_native": "Ask the bank which rule applies to this district.",
            "explanation_en": "Ask the bank which rule applies to this district.",
            "next_steps": [{"title": "Request the written service-area rule", "detail": "Ask for the specific policy and review contact."}],
            "questions_for_user": [], "legal_context": None
        }
        text = "My district is outside the bank's service area, but the notice gives no policy clause or review contact."
        with patch("main._generate_async", new=AsyncMock(return_value=payload)):
            response = TestClient(main.app).post("/analyse/text", json={"text": text})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertIsNone(result["bias_score"])
        labels = {item["label"] for item in result["bias_indicators"]}
        self.assertIn("Reason is too general to verify", labels)
        self.assertIn("Decision basis or review route is missing", labels)

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

    def test_invalid_structured_output_retries_with_stable_model(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        calls = Mock(side_effect=[SimpleNamespace(text="not-json"), SimpleNamespace(text='{"ok": true}')])
        client = SimpleNamespace(models=SimpleNamespace(generate_content=calls))
        with patch.object(main, "MODEL", "test-primary"), patch.object(main, "_client", return_value=client):
            result = main._generate("synthetic case", "system prompt")
        self.assertEqual(result, {"ok": True})
        used = [call.kwargs["model"] for call in calls.call_args_list]
        self.assertEqual(used, ["test-primary", "gemini-3.5-flash-lite"])

if __name__ == "__main__":
    unittest.main()
