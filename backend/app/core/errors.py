"""One common error shape. Messages must never contain raw PII."""
from typing import Optional

STATUS = {
    "INVALID_REQUEST": 400, "INVALID_DOCUMENT": 400, "UNSUPPORTED_FILE": 415,
    "INPUT_TOO_LARGE": 413, "PII_PROCESSING_FAILED": 422,
    "LLM_PROVIDER_ERROR": 502, "LLM_PROVIDER_TIMEOUT": 504, "REINSERTION_FAILED": 500,
    "PRIVACY_ENGINE_UNAVAILABLE": 503, "OUTBOUND_PII_LEAKAGE_BLOCKED": 409, "INTERNAL_ERROR": 500,
}
SAFE_MESSAGE = {
    "INVALID_REQUEST": "Missing or invalid text, task or provider.",
    "INVALID_DOCUMENT": "The uploaded Word document is invalid or contains no readable text.",
    "UNSUPPORTED_FILE": "Upload a Word .docx document.",
    "INPUT_TOO_LARGE": "Input exceeds the configured size limit.",
    "PII_PROCESSING_FAILED": "Local PII detection or masking failed.",
    "LLM_PROVIDER_ERROR": "The external LLM provider returned an error.",
    "LLM_PROVIDER_TIMEOUT": "The external LLM provider timed out.",
    "REINSERTION_FAILED": "Local placeholder reinsertion failed.",
    "PRIVACY_ENGINE_UNAVAILABLE": "The local privacy engine is unavailable.",
    "OUTBOUND_PII_LEAKAGE_BLOCKED": "The request was blocked because the outbound payload failed the privacy check.",
    "INTERNAL_ERROR": "Unexpected internal error.",
}


class GatewayError(Exception):
    def __init__(self, code: str, request_id: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(code)
        self.code = code
        self.http_status = STATUS.get(code, 500)
        self.message = SAFE_MESSAGE.get(code, SAFE_MESSAGE["INTERNAL_ERROR"])
        self.request_id = request_id
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message,
                          "request_id": self.request_id, "details": self.details}}
