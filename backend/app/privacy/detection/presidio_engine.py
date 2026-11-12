"""Microsoft Presidio integration (optional at runtime, REQUIRED by the problem statement).

Our India recognizers are wrapped as Presidio EntityRecognizers and run inside a real
AnalyzerEngine, so Presidio is the orchestrator. Presidio's own built-in India
recognizers (IN_AADHAAR, IN_PAN, IN_PASSPORT, IN_VOTER) are ALSO loaded when
available and their hits are merged (union) with ours. Presidio has no GSTIN
recognizer, so GSTIN is always ours.

Enable with env PRIVACY_USE_PRESIDIO=1. Needs:
    pip install presidio-analyzer spacy && python -m spacy download en_core_web_sm
NOT exercised in the offline build sandbox: run tests/privacy/test_presidio_optional.py once installed.
"""
import os
from typing import List, Optional

from ..schemas import Span
from . import india_recognizers as ir

# Presidio entity name -> our canonical name
PRESIDIO_MAP = {
    "IN_AADHAAR": "AADHAAR", "IN_PAN": "PAN", "IN_PASSPORT": "PASSPORT", "IN_VOTER": "VOTER_ID",
    "GSTIN": "GSTIN", "PERSON": "PERSON",
}

_analyzer = None
_failed = False


def _build():
    from presidio_analyzer import AnalyzerEngine, EntityRecognizer, RecognizerRegistry, RecognizerResult
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    class FnRecognizer(EntityRecognizer):
        def __init__(self, entity: str, fn):
            super().__init__(supported_entities=[entity], name=f"Custom{entity}Recognizer", supported_language="en")
            self._fn = fn

        def load(self):  # nothing to load
            pass

        def analyze(self, text, entities, nlp_artifacts=None):
            return [RecognizerResult(entity_type=s.type, start=s.start, end=s.end, score=s.confidence)
                    for s in self._fn(text)]

    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": os.getenv("SPACY_MODEL", "en_core_web_sm")}],
    }).create_engine()

    registry = RecognizerRegistry()
    # Built-in India recognizers (names verified against Presidio docs; skip any missing in your version)
    for cls_name in ("InAadhaarRecognizer", "InPanRecognizer", "InPassportRecognizer", "InVoterRecognizer"):
        try:
            import presidio_analyzer.predefined_recognizers as pr
            registry.add_recognizer(getattr(pr, cls_name)())
        except Exception:
            pass
    # Our validated recognizers (always, incl. GSTIN)
    for ent, fn in ir.ALL_FINDERS.items():
        registry.add_recognizer(FnRecognizer(ent, fn))
    return AnalyzerEngine(nlp_engine=nlp, registry=registry, supported_languages=["en"])


def get_analyzer():
    global _analyzer, _failed
    if _failed:
        return None
    if _analyzer is None:
        try:
            _analyzer = _build()
        except Exception:
            _failed = True
            return None
    return _analyzer


def presidio_enabled() -> bool:
    return os.getenv("PRIVACY_USE_PRESIDIO", "0") == "1"


def detect_with_presidio(text: str) -> List[Span]:
    az = get_analyzer()
    if az is None:
        return []
    out: List[Span] = []
    for r in az.analyze(text=text, language="en", score_threshold=0.3):
        typ = PRESIDIO_MAP.get(r.entity_type)
        if typ:
            out.append(Span(r.start, r.end, typ, float(r.score), "presidio"))
    return out
