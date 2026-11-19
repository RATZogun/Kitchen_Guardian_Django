from django.urls import path

from . import views

app_name = "compras"

urlpatterns = [
    path("", views.ListaLista.as_view(), name="listas"),
    path("nova/", views.ListaCriar.as_view(), name="lista_nova"),
    path("gerar/", views.gerar_lista, name="gerar"),
    path("<int:pk>/", views.ListaDetalhe.as_view(), name="lista"),
    path("<int:pk>/editar/", views.ListaEditar.as_view(), name="lista_editar"),
    path("<int:pk>/excluir/", views.ListaExcluir.as_view(), name="lista_excluir"),
    path("<int:lista>/itens/novo/", views.ItemCriar.as_view(), name="item_novo"),
    path("itens/<int:pk>/editar/", views.ItemEditar.as_view(), name="item_editar"),
    path("itens/<int:pk>/excluir/", views.ItemExcluir.as_view(), name="item_excluir"),
    path("itens/<int:pk>/comprado/", views.alternar_comprado, name="item_comprado"),
]
