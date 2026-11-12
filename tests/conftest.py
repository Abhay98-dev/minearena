"""Use the dependency-free local detector by default in the offline test suite."""
import os

# Model loading and external downloads are checked separately; unit/API tests
# must stay deterministic even when a developer's .env enables optional models.
os.environ["PRIVACY_NER"] = "heuristic"
os.environ["PRIVACY_USE_PRESIDIO"] = "0"
os.environ["PRIVACY_PRELOAD"] = "0"
