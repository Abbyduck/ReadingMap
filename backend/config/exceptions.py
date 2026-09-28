from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler as drf_exception_handler

def exception_handler(exc, context):
    if isinstance(exc, IntegrityError):
        return Response({"detail": "数据与现有记录冲突，请刷新后重试。"}, status=409)
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(getattr(exc, "message_dict", None) or exc.messages)
    return drf_exception_handler(exc, context)
