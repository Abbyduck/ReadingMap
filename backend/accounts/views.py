import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import csrf_protect
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from .models import User

logger = logging.getLogger(__name__)

class AuthThrottle(AnonRateThrottle):
    scope = "auth"
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}

class ResetThrottle(AuthThrottle):
    scope = "password_reset"

def user_data(user):
    if not user.is_authenticated:
        return None
    return {"id": user.pk, "email": user.email, "name": user.name, "is_staff": user.is_staff}

class Credentials(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    name = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate_email(self, value):
        return value.strip().lower()

def check_password(password, user):
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"password": exc.messages}) from exc

@method_decorator(csrf_protect, name="dispatch")
class PublicAuthView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

class CsrfView(PublicAuthView):
    throttle_classes = []
    def get(self, request):
        response = Response({"csrfToken": get_token(request)})
        response["Cache-Control"] = "no-store"
        return response

class MeView(CsrfView):
    def get(self, request):
        response = Response({"user": user_data(request.user)})
        response["Cache-Control"] = "no-store"
        return response

class RegisterView(PublicAuthView):
    def post(self, request):
        serializer = Credentials(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User(email=data["email"], name=data.get("name", ""))
        check_password(data["password"], user)
        try:
            with transaction.atomic():
                user.set_password(data["password"])
                user.save()
        except IntegrityError:
            raise serializers.ValidationError({"email": ["此邮箱无法注册，请尝试登录或重置密码。"]})
        login(request, user)
        return Response({"user": user_data(user)}, status=201)

class LoginView(PublicAuthView):
    def post(self, request):
        serializer = Credentials(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = authenticate(request, email=data["email"], password=data["password"])
        if user is None:
            return Response({"detail": "邮箱或密码不正确。"}, status=400)
        login(request, user)
        return Response({"user": user_data(user)})

class LogoutView(PublicAuthView):
    throttle_classes = []
    def post(self, request):
        logout(request)
        return Response(status=204)

class ResetRequest(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

class ResetView(PublicAuthView):
    throttle_classes = [ResetThrottle]
    def post(self, request):
        serializer = ResetRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"].strip(), is_active=True).first()
        if user and user.has_usable_password():
            query = urlencode({"uid": urlsafe_base64_encode(force_bytes(user.pk)), "token": default_token_generator.make_token(user)})
            link = f"{settings.FRONTEND_ORIGIN}/reset-password?{query}"
            try:
                send_mail("Reading Map · 重置密码", f"请在一小时内打开此链接重置密码：\n\n{link}\n\n如果不是你申请的，请忽略此邮件。", settings.DEFAULT_FROM_EMAIL, [user.email])
            except Exception:
                # Never leak whether an address exists or include reset tokens in logs.
                logger.error("Password reset email delivery failed; check email backend configuration.")
        return Response({"detail": "如果邮箱已注册，你将收到重置密码的邮件。"})

class ConfirmRequest(serializers.Serializer):
    uid = serializers.CharField(max_length=128)
    token = serializers.CharField(max_length=128)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

class ResetConfirmView(PublicAuthView):
    throttle_classes = [ResetThrottle]
    def post(self, request):
        serializer = ConfirmRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user_id = urlsafe_base64_decode(data["uid"]).decode()
            if not user_id.isdigit():
                raise ValueError
        except (ValueError, UnicodeDecodeError, OverflowError):
            user_id = None
        with transaction.atomic():
            user = User.objects.select_for_update().filter(pk=user_id, is_active=True).first() if user_id else None
            if user is None or not default_token_generator.check_token(user, data["token"]):
                return Response({"detail": "重置链接无效或已过期，请重新申请。"}, status=400)
            check_password(data["password"], user)
            user.set_password(data["password"])
            user.save(update_fields=["password"])
        logout(request)
        return Response({"detail": "密码已更新，请使用新密码登录。"})
