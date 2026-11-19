"""Área do usuário: produtos, lotes (entrada, baixa e edição) e movimentações."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView

from apps.core.mixins import AreaMixin, ExclusaoProtegidaMixin, FormCozinhaMixin, escopo

from . import services
from .forms import BaixaForm, LoteEdicaoForm, LoteEntradaForm, ProdutoForm
from .models import (ABAIXO_DO_MINIMO, Categoria, Lote, Movimentacao, Produto, hoje,
                     limite_alerta)


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
        if g.get("nivel") == "BAIXO":
            qs = qs.filter(ABAIXO_DO_MINIMO)
        elif g.get("nivel") == "ZERADO":
            qs = qs.filter(saldo=0)
        elif g.get("nivel") == "OK":
            qs = qs.exclude(ABAIXO_DO_MINIMO).filter(saldo__gt=0)
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


# ---------------------------------------------------------------------------
# Lotes
# ---------------------------------------------------------------------------
class LoteLista(AreaMixin, ListView):
    permission_required = "estoque.view_lote"
    template_name = "estoque/lote_lista.html"
    paginate_by = 20
    campo_cozinha = "produto__cozinha"

    def get_queryset(self):
        qs = escopo(self.request.user, Lote.objects.all(), self.campo_cozinha) \
            .select_related("produto", "local")
        g = self.request.GET
        situacao = g.get("situacao", "COM_SALDO")
        filtros = {
            "COM_SALDO": Q(quantidade_atual__gt=0),
            "VENCIDO": Q(quantidade_atual__gt=0, data_validade__lt=hoje()),
            "VENCENDO": Q(quantidade_atual__gt=0, data_validade__gte=hoje(),
                          data_validade__lte=limite_alerta()),
            "ESGOTADO": Q(quantidade_atual=0),
        }
        if situacao in filtros:
            qs = qs.filter(filtros[situacao])
        if g.get("q"):
            qs = qs.filter(Q(produto__nome__icontains=g["q"]) | Q(codigo__icontains=g["q"]))
        if g.get("local"):
            qs = qs.filter(local__tipo=g["local"])
        return qs

    def get_context_data(self, **kwargs):
        from apps.cozinhas.models import LocalArmazenamento
        return super().get_context_data(situacao=self.request.GET.get("situacao", "COM_SALDO"),
                                        tipos_local=LocalArmazenamento.Tipo.choices, **kwargs)


class LoteEntrada(AreaMixin, FormCozinhaMixin, CreateView):
    permission_required = "estoque.add_lote"
    model = Lote
    form_class = LoteEntradaForm
    template_name = "generico/form.html"
    extra_context = {"titulo": "Registrar entrada de mercadoria", "voltar": "estoque:lotes",
                     "botao": "Registrar entrada",
                     "ajuda": "Cada entrada vira um lote com validade e local próprios."}

    def get_initial(self):
        return {"produto": self.request.GET.get("produto"), "data_entrada": hoje()}

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["produto"].queryset = form.fields["produto"].queryset.filter(ativo=True)
        return form

    def form_valid(self, form):
        try:
            services.registrar_entrada(form.instance, self.request.user,
                                       motivo=form.cleaned_data["motivo"],
                                       observacao=form.cleaned_data["observacao"])
        except ValidationError as erro:
            form.add_error(None, erro)
            return self.form_invalid(form)
        self.object = form.instance
        messages.success(self.request, f"Entrada registrada: {self.object}.")
        return redirect("estoque:produto", self.object.produto_id)


class LoteEditar(AreaMixin, FormCozinhaMixin, UpdateView):
    permission_required = "estoque.change_lote"
    model = Lote
    form_class = LoteEdicaoForm
    template_name = "generico/form.html"
    campo_cozinha = "produto__cozinha"
    extra_context = {"titulo": "Editar lote", "voltar": "estoque:lotes",
                     "ajuda": "A quantidade só muda por entradas, saídas e descartes."}

    def get_success_url(self):
        messages.success(self.request, "Lote atualizado.")
        return reverse("estoque:produto", args=[self.object.produto_id])


class LoteBaixa(AreaMixin, FormView):
    """Saída por consumo ou descarte de um lote (RF011)."""
    permission_required = "estoque.add_movimentacao"
    form_class = BaixaForm
    template_name = "estoque/lote_baixa.html"

    @cached_property
    def lote(self):
        # só é acessado depois que AreaMixin conferiu login e permissão
        return get_object_or_404(
            escopo(self.request.user, Lote.objects.select_related("produto", "local"),
                   "produto__cozinha"), pk=self.kwargs["pk"])

    def get_initial(self):
        return {"data": hoje(), "quantidade": None}

    def get_context_data(self, **kwargs):
        return super().get_context_data(lote=self.lote, **kwargs)

    def form_valid(self, form):
        d = form.cleaned_data
        try:
            services.registrar_baixa(self.lote, d["quantidade"], self.request.user,
                                     tipo=d["tipo"], motivo=d["motivo"], data=d["data"],
                                     observacao=d["observacao"])
        except ValidationError as erro:
            for campo, msgs in erro.message_dict.items() if hasattr(erro, "error_dict") \
                    else [(None, erro.messages)]:
                for msg in msgs:
                    form.add_error(campo if campo in form.fields else None, msg)
            return self.form_invalid(form)
        messages.success(self.request, "Baixa registrada.")
        return redirect("estoque:produto", self.lote.produto_id)


# ---------------------------------------------------------------------------
# Movimentações (somente leitura: o histórico é imutável)
# ---------------------------------------------------------------------------
class MovimentacaoLista(AreaMixin, ListView):
    permission_required = "estoque.view_movimentacao"
    template_name = "estoque/movimentacao_lista.html"
    paginate_by = 25

    def get_queryset(self):
        qs = escopo(self.request.user, Movimentacao.objects.all(), "lote__produto__cozinha") \
            .select_related("lote__produto", "usuario")
        g = self.request.GET
        if g.get("tipo") in Movimentacao.Tipo.values:
            qs = qs.filter(tipo=g["tipo"])
        if g.get("de"):
            qs = qs.filter(data__gte=g["de"])
        if g.get("ate"):
            qs = qs.filter(data__lte=g["ate"])
        if g.get("q"):
            qs = qs.filter(lote__produto__nome__icontains=g["q"])
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(tipos=Movimentacao.Tipo.choices, **kwargs)
