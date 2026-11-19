from django.urls import path

from . import views

app_name = "estoque"

urlpatterns = [
    path("produtos/", views.ProdutoLista.as_view(), name="produtos"),
    path("produtos/novo/", views.ProdutoCriar.as_view(), name="produto_novo"),
    path("produtos/<int:pk>/", views.ProdutoDetalhe.as_view(), name="produto"),
    path("produtos/<int:pk>/editar/", views.ProdutoEditar.as_view(), name="produto_editar"),
    path("produtos/<int:pk>/excluir/", views.ProdutoExcluir.as_view(), name="produto_excluir"),
]
