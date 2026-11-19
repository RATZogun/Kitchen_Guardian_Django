from django.urls import path

from . import views

app_name = "cozinhas"

urlpatterns = [
    path("locais/", views.LocalLista.as_view(), name="locais"),
    path("locais/novo/", views.LocalCriar.as_view(), name="local_novo"),
    path("locais/<int:pk>/editar/", views.LocalEditar.as_view(), name="local_editar"),
    path("locais/<int:pk>/excluir/", views.LocalExcluir.as_view(), name="local_excluir"),
]
