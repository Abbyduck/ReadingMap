from django.urls import path
from .views import CsrfView, MeView, RegisterView, LoginView, LogoutView, ResetView, ResetConfirmView
urlpatterns = [
    path("csrf", CsrfView.as_view()), path("me", MeView.as_view()),
    path("register", RegisterView.as_view()), path("login", LoginView.as_view()),
    path("logout", LogoutView.as_view()), path("password-reset", ResetView.as_view()),
    path("password-reset/confirm", ResetConfirmView.as_view()),
]
