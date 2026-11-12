"""Offline coverage for the additive GLiNER/Presidio integration (no model downloads)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

pytest.importorskip("presidio_analyzer")

from app.privacy import destroy_mapping, sanitize_document  # noqa: E402
from app.privacy.detection import india_recognizers as ir  # noqa: E402
from app.privacy.detection import ner_engine, presidio_engine  # noqa: E402


class FakeModel:
    def __init__(self, spans=None, fail=False):
        self.spans = spans or []
        self.fail = fail

    def predict(self, text):
        if self.fail:
            raise RuntimeError("simulated model failure")
        return self.spans


def test_custom_recognizer_maps_gliner_predictions_and_ignores_bad_spans(monkeypatch):
    monkeypatch.setattr(ner_engine, "get_gliner", lambda: FakeModel([
        ner_engine.Span(0, 12, "ORGANIZATION", 0.87, "gliner"),
        ner_engine.Span(11, 15, "LOCATION", 0.72, "gliner"),
        ner_engine.Span(-1, 4, "PERSON", 0.8, "gliner"),
    ]))
    recognizer = presidio_engine._make_gliner_recognizer()
    results = recognizer.analyze("Government Pune", ["ORGANIZATION", "LOCATION", "PERSON"])
    assert [(r.entity_type, r.start, r.end, r.score) for r in results] == [
        ("ORGANIZATION", 0, 12, 0.87), ("LOCATION", 11, 15, 0.72)]


def test_gliner_is_added_to_existing_presidio_registry(monkeypatch):
    import presidio_analyzer
    import presidio_analyzer.nlp_engine

    holder = {}

    class Registry:
        def __init__(self):
            self.recognizers = []
            holder["registry"] = self

        def add_recognizer(self, recognizer):
            self.recognizers.append(recognizer)

    class Provider:
        def __init__(self, nlp_configuration):
            pass

        def create_engine(self):
            return object()

    class Analyzer:
        def __init__(self, nlp_engine, registry, supported_languages):
            self.registry = registry

    monkeypatch.setattr(presidio_analyzer, "RecognizerRegistry", Registry)
    monkeypatch.setattr(presidio_analyzer, "AnalyzerEngine", Analyzer)
    monkeypatch.setattr(presidio_analyzer.nlp_engine, "NlpEngineProvider", Provider)
    monkeypatch.setattr(presidio_engine, "_analyzer", None)
    monkeypatch.setattr(presidio_engine, "_failed", False)
    analyzer = presidio_engine._build()
    registered = holder["registry"].recognizers
    assert analyzer.registry is holder["registry"]
    assert any(r.name == "GLiNERContextRecognizer" for r in registered)
    assert any(r.name == "CustomPANRecognizer" for r in registered)


def test_combined_regex_and_gliner_results_mask_through_existing_pipeline(monkeypatch):
    text = "Abhay Chachar at Government College of Engineering lives in Pune. Email abhay@gmail.com, phone 9876543210."
    model = FakeModel([
        ner_engine.Span(text.index("Abhay"), text.index("Abhay") + len("Abhay Chachar"), "PERSON", 0.91, "gliner"),
        ner_engine.Span(text.index("Government"), text.index("Government") + len("Government College of Engineering"), "ORGANIZATION", 0.9, "gliner"),
        ner_engine.Span(text.index("Pune"), text.index("Pune") + len("Pune"), "LOCATION", 0.88, "gliner"),
    ])
    monkeypatch.setattr(ner_engine, "get_gliner", lambda: model)
    spans = model.predict(text) + ir.find_email(text) + ir.find_phone(text)
    monkeypatch.setattr(presidio_engine, "presidio_enabled", lambda: True)
    monkeypatch.setattr(presidio_engine, "detect_with_presidio", lambda _: spans)
    result = sanitize_document(text, "combined-gliner-presidio")
    detected = {e["type"] for e in result["entities"]}
    assert {"PERSON", "ORGANIZATION", "LOCATION", "EMAIL_ADDRESS", "PHONE_NUMBER"} <= detected
    for value in ("Abhay Chachar", "Government College of Engineering", "Pune", "abhay@gmail.com", "9876543210"):
        assert value not in result["sanitized_text"]
    destroy_mapping(result["mapping_handle"])


def test_gliner_inference_failure_does_not_disable_regex_detection(monkeypatch):
    monkeypatch.setattr(ner_engine, "get_gliner", lambda: FakeModel(fail=True))
    assert ner_engine.detect_names_addresses("My name is Abhay Chachar.")  # heuristic remains
    assert ir.find_email("Email abhay@gmail.com")
    assert ir.find_phone("Phone 9876543210")


@pytest.mark.parametrize("text,expected", [
    ("My email is abhay@gmail.com", "EMAIL_ADDRESS"),
    ("My phone number is 9876543210", "PHONE_NUMBER"),
    ("Call +91 98765 43210", "PHONE_NUMBER"),
])
def test_email_and_indian_phone_regex_types(text, expected):
    spans = ir.find_all_structured(text)
    assert any(span.type == expected and span.end > span.start for span in spans)
