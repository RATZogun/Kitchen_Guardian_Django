"""Área do usuário: listas de compras e seus itens."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.core.forms import BootstrapMixin
from apps.core.mixins import (AreaMixin, ExclusaoProtegidaMixin, FormCozinhaMixin, eh_admin_geral,
                              escopo, restringir_campos)

from .models import ItemListaCompra, ListaCompra
from .services import gerar_lista_reposicao


class ListaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ListaCompra
        fields = ["cozinha", "titulo", "status", "data_prevista", "observacoes"]
        widgets = {"data_prevista": forms.DateInput(), "observacoes": forms.Textarea(attrs={"rows": 3})}


class ItemForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = ItemListaCompra
        fields = ["produto", "quantidade", "fornecedor", "preco_estimado", "comprado"]

    def __init__(self, *args, lista, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.lista = lista
        # o produto atual do item continua na lista mesmo se tiver sido desativado depois
        self.fields["produto"].queryset = self.fields["produto"].queryset.filter(
            Q(ativo=True) | Q(pk=self.instance.produto_id), cozinha=lista.cozinha_id)

    def clean_produto(self):
        produto = self.cleaned_data["produto"]
        repetido = self.instance.lista.itens.filter(produto=produto).exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Este produto já está na lista; edite o item existente.")
        return produto


def _listas(user):
    return escopo(user, ListaCompra.objects.select_related("cozinha"))


# ---------------------------------------------------------------------------
# Listas
# ---------------------------------------------------------------------------
class ListaLista(AreaMixin, ListView):
    permission_required = "compras.view_listacompra"
    model = ListaCompra
    template_name = "compras/lista_lista.html"
    paginate_by = 15

    def get_queryset(self):
        qs = super().get_queryset().select_related("cozinha", "criada_por").com_resumo()
        if self.request.GET.get("status") in ListaCompra.Status.values:
            qs = qs.filter(status=self.request.GET["status"])
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(status=ListaCompra.Status.choices, **kwargs)


class ListaDetalhe(AreaMixin, DetailView):
    permission_required = "compras.view_listacompra"
    model = ListaCompra
    template_name = "compras/lista_detalhe.html"

    def get_context_data(self, **kwargs):
        itens = self.object.itens.select_related("produto", "fornecedor")
        form = None
        if self.request.user.has_perm("compras.add_itemlistacompra"):
            form = restringir_campos(ItemForm(lista=self.object), self.request.user)
        return super().get_context_data(itens=itens, form_item=form, **kwargs)


class ListaCriar(AreaMixin, FormCozinhaMixin, CreateView):
    permission_required = "compras.add_listacompra"
    model = ListaCompra
    form_class = ListaForm
    template_name = "generico/form.html"
    extra_context = {"titulo": "Nova lista de compras", "voltar": "compras:listas"}

    def form_valid(self, form):
        form.instance.criada_por = self.request.user
        messages.success(self.request, "Lista criada. Agora adicione os itens.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("compras:lista", args=[self.object.pk])


class ListaEditar(AreaMixin, FormCozinhaMixin, UpdateView):
    permission_required = "compras.change_listacompra"
    model = ListaCompra
    form_class = ListaForm
    template_name = "generico/form.html"
    extra_context = {"titulo": "Editar lista de compras", "voltar": "compras:listas"}

    def get_success_url(self):
        messages.success(self.request, "Lista atualizada.")
        return reverse("compras:lista", args=[self.object.pk])


class ListaExcluir(AreaMixin, ExclusaoProtegidaMixin, DeleteView):
    permission_required = "compras.delete_listacompra"
    model = ListaCompra
    template_name = "generico/confirmar_exclusao.html"
    success_url = reverse_lazy("compras:listas")


@login_required
@permission_required("compras.add_listacompra", raise_exception=True)
@require_POST
def gerar_lista(request):
    """Cria a lista de reposição com o que está abaixo do mínimo na cozinha do usuário."""
    if eh_admin_geral(request.user) and not request.user.cozinha_id:
        messages.warning(request, "Gere a lista entrando com um usuário de uma cozinha.")
        return redirect("compras:listas")
    lista = gerar_lista_reposicao(request.user.cozinha, request.user)
    if lista is None:
        messages.info(request, "Nenhum produto está abaixo do estoque mínimo. Nada a repor!")
        return redirect("compras:listas")
    messages.success(request, f"Lista gerada com {lista.itens.count()} item(ns).")
    return redirect("compras:lista", lista.pk)


# ---------------------------------------------------------------------------
# Itens
# ---------------------------------------------------------------------------
class ItemMixin(AreaMixin):
    campo_cozinha = "lista__cozinha"
    model = ItemListaCompra

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["lista"] = self.lista
        return kwargs

    def get_form(self, form_class=None):
        return restringir_campos(super().get_form(form_class), self.request.user)

    def get_success_url(self):
        return reverse("compras:lista", args=[self.lista.pk])

    def get_context_data(self, **kwargs):
        return super().get_context_data(voltar_url=self.get_success_url(), **kwargs)


class ItemCriar(ItemMixin, CreateView):
    permission_required = "compras.add_itemlistacompra"
    form_class = ItemForm
    template_name = "generico/form.html"
    extra_context = {"titulo": "Adicionar item"}

    @cached_property
    def lista(self):
        # só é acessado depois que AreaMixin conferiu login e permissão
        return get_object_or_404(_listas(self.request.user), pk=self.kwargs["lista"])

    def form_valid(self, form):
        messages.success(self.request, "Item adicionado.")
        return super().form_valid(form)


class ItemEditar(ItemMixin, UpdateView):
    # o operador tem change_itemlistacompra só para marcar itens comprados
    permission_required = ("compras.change_itemlistacompra", "compras.change_listacompra")
    form_class = ItemForm
    template_name = "generico/form.html"
    extra_context = {"titulo": "Editar item"}

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        self.lista = obj.lista
        return obj


class ItemExcluir(ItemMixin, DeleteView):
    permission_required = "compras.delete_itemlistacompra"
    template_name = "generico/confirmar_exclusao.html"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        self.lista = obj.lista
        return obj

    def get_form_kwargs(self):   # DeleteView usa um Form simples, sem "lista"
        return super(ItemMixin, self).get_form_kwargs()

    def get_form(self, form_class=None):
        return super(ItemMixin, self).get_form(form_class)


@login_required
@permission_required("compras.change_itemlistacompra", raise_exception=True)
@require_POST
def alternar_comprado(request, pk):
    item = get_object_or_404(escopo(request.user, ItemListaCompra.objects.all(), "lista__cozinha"),
                             pk=pk)
    item.comprado = not item.comprado
    item.save(update_fields=["comprado"])
    return redirect("compras:lista", item.lista_id)
