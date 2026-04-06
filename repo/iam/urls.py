from django.urls import include, path
from rest_framework.routers import DefaultRouter

from iam.views import LoginView, LogoutView, MeView, PasswordChangeView, UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("password/change/", PasswordChangeView.as_view(), name="auth-password-change"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("", include(router.urls)),
]
