from django.contrib import admin
from django.urls import include, path

admin.site.site_title = "Guardião da Cozinha"
admin.site.site_header = "Guardião da Cozinha"
admin.site.index_title = "Painel"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
]
