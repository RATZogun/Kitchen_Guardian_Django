"""Área do usuário: produtos."""
from django.contrib import messages
from django.db.models import Q
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.mixins import AreaMixin, ExclusaoProtegidaMixin, FormCozinhaMixin, escopo

from .forms import ProdutoForm
from .models import Categoria, Movimentacao, Produto


# ---------------------------------------------------------------------------
# Produtos
# ---------------------------------------------------------------------------
class ProdutoLista(AreaMixin, ListView):
    permission_required = "estoque.view_produto"
    template_name = "estoque/produto_lista.html"
    paginate_by = 15

    def get_queryset(self):
        qs = escopo(self.request.user, Produto.objects.com_saldo(), "cozinha") \
            .select_related("categoria", "cozinha")
        g = self.request.GET
        if g.get("q"):
            qs = qs.filter(Q(nome__icontains=g["q"]) | Q(codigo_barras=g["q"]))
        if g.get("categoria"):
            qs = qs.filter(categoria_id=g["categoria"])
        if g.get("nivel") in ("OK", "BAIXO", "ZERADO"):
            qs = qs.filter(nivel=g["nivel"])
        if g.get("inativos") != "1":
            qs = qs.filter(ativo=True)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(categorias=Categoria.objects.filter(ativo=True), **kwargs)


class ProdutoDetalhe(AreaMixin, DetailView):
    permission_required = "estoque.view_produto"
    template_name = "estoque/produto_detalhe.html"

    def get_queryset(self):
        return escopo(self.request.user, Produto.objects.com_saldo(), "cozinha")

    def get_context_data(self, **kwargs):
        p = self.object
        return super().get_context_data(
            lotes=p.lotes.com_saldo().select_related("local", "fornecedor"),
            movimentacoes=Movimentacao.objects.filter(lote__produto=p)
                .select_related("lote", "usuario")[:10],
            **kwargs)


class ProdutoCriar(AreaMixin, FormCozinhaMixin, CreateView):
    permission_required = "estoque.add_produto"
    model = Produto
    form_class = ProdutoForm
    template_name = "generico/form.html"
    extra_context = {"titulo": "Novo produto", "voltar": "estoque:produtos"}

    def form_valid(self, form):
        form.instance.criado_por = self.request.user
        messages.success(self.request, "Produto cadastrado.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("estoque:produto", args=[self.object.pk])


class ProdutoEditar(AreaMixin, FormCozinhaMixin, UpdateView):
    permission_required = "estoque.change_produto"
    model = Produto
    form_class = ProdutoForm
    template_name = "generico/form.html"
    extra_context = {"titulo": "Editar produto", "voltar": "estoque:produtos"}

    def form_valid(self, form):
        messages.success(self.request, "Produto atualizado.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("estoque:produto", args=[self.object.pk])


class ProdutoExcluir(AreaMixin, ExclusaoProtegidaMixin, DeleteView):
    permission_required = "estoque.delete_produto"
    model = Produto
    template_name = "generico/confirmar_exclusao.html"
    success_url = reverse_lazy("estoque:produtos")
