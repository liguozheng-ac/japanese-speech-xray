"""Safe error taxonomy; diagnostic exception strings never enter HTTP."""
from .models import ErrorResponse, ErrorDetails

ERRORS = {
    'UNSUPPORTED_FORMAT': (422, 'Only mono PCM16 RIFF WAV is supported.'),
    'INVALID_AUDIO': (422, 'Audio could not be validated.'),
    'UNKNOWN_PROMPT': (404, 'Prompt ID is unknown.'),
    'UPLOAD_TOO_LARGE': (413, 'Upload exceeds the configured resource limit.'),
    'AUDIO_TOO_LONG': (422, 'Audio exceeds the configured duration limit.'),
    'ALIGNMENT_RUNTIME_UNAVAILABLE': (503, 'Alignment runtime is unavailable.'),
    'REFERENCE_ARTIFACT_MISSING': (503, 'A required reference artifact is unavailable.'),
    'SERVICE_BUSY': (503, 'Analysis capacity is occupied; retry after the current request.'),
    'ANALYSIS_TIMEOUT': (503, 'Analysis exceeded the configured execution limit.'),
    'ANALYSIS_CANCELLED': (409, 'Analysis was cancelled; worker resources have been released.'),
    'INVALID_REQUEST': (422, 'Multipart audio and prompt_id fields are required.'),
    'INTERNAL_PIPELINE_ERROR': (500, 'An internal pipeline operation failed.'),
}


class ProductError(Exception):
    def __init__(self, code, stage=None, reason=None):
        self.code, self.stage, self.reason = code, stage, reason
        super().__init__(code)

    @property
    def http_status(self):
        return ERRORS[self.code][0]

    def response(self, request_id):
        return ErrorResponse(error_code=self.code, message=ERRORS[self.code][1], request_id=request_id,
                             details=ErrorDetails(stage=self.stage, reason_code=self.reason))
