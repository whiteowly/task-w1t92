from datetime import datetime, timezone

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _build_error_payload(code: str, message: str, details, request_id: str | None):
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }


class DomainAPIException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "common.domain_error"
    default_detail = "Domain rule violation."

    def __init__(self, *, code: str, message: str, details=None, status_code=None):
        super().__init__(detail=message)
        self.error_code = code
        self.error_message = message
        self.error_details = details or []
        if status_code is not None:
            self.status_code = status_code


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    request = context.get("request")
    request_id = getattr(request, "request_id", None)

    if isinstance(exc, DomainAPIException):
        payload = _build_error_payload(
            code=exc.error_code,
            message=exc.error_message,
            details=exc.error_details,
            request_id=request_id,
        )
        return Response(payload, status=exc.status_code)

    if response is None:
        payload = _build_error_payload(
            code="common.internal_error",
            message="An unexpected error occurred.",
            details=[],
            request_id=request_id,
        )
        return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if isinstance(response.data, dict):
        details = []
        if "detail" in response.data:
            message = str(response.data["detail"])
        else:
            message = "Validation failed."
            for key, value in response.data.items():
                if isinstance(value, list):
                    for item in value:
                        details.append(
                            {"field": key, "code": "invalid", "message": str(item)}
                        )
                else:
                    details.append(
                        {"field": key, "code": "invalid", "message": str(value)}
                    )
        code = (
            "common.validation_error"
            if response.status_code == 400
            else "common.request_error"
        )
    else:
        message = str(response.data)
        code = "common.request_error"
        details = []

    response.data = _build_error_payload(
        code=code, message=message, details=details, request_id=request_id
    )
    return response
