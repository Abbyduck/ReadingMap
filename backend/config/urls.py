from django.contrib import admin
from django.http import JsonResponse, FileResponse, Http404
from django.urls import include, path
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser

admin.site.site_header = "Reading Map 管理"
admin.site.site_title = "Reading Map"
admin.site.index_title = "资料与用户管理"

@api_view(["GET"])
@permission_classes([IsAdminUser])
def booklist_asset(request, asset_path):
    root = settings.BOOKLIST_ROOT.resolve()
    target = (root / asset_path).resolve()
    if not target.is_relative_to(root) or not target.is_file() or target.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise Http404
    response = FileResponse(target.open("rb"))
    response["Cache-Control"] = "private, no-store"
    return response

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/review/", include("reviews.urls")),
    path("api/", include("catalog.urls")),
    path("booklist-assets/<path:asset_path>", booklist_asset),
]
