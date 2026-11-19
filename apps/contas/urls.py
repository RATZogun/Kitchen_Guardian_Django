from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "contas"

urlpatterns = [
    path("entrar/", views.EntrarView.as_view(), name="login"),
    path("sair/", LogoutView.as_view(), name="logout"),
    path("cadastre-se/", views.cadastro, name="cadastro"),
    path("perfil/", views.perfil, name="perfil"),
    path("perfil/senha/", views.alterar_senha, name="senha"),
]
