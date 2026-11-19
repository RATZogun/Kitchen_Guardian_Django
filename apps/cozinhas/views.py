"""Área do usuário: locais de armazenamento da cozinha (despensa, geladeira...)."""
from django import forms
from django.contrib import messages
from django.db.models import Count, Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.forms import BootstrapMixin, NomeUnicoNaCozinhaMixin
from apps.core.mixins import AreaMixin, ExclusaoProtegidaMixin, FormCozinhaMixin

from .models import LocalArmazenamento


class LocalForm(BootstrapMixin, NomeUnicoNaCozinhaMixin, forms.ModelForm):
    class Meta:
        model = LocalArmazenamento
        fields = ["cozinha", "nome", "tipo", "temperatura_min", "temperatura_max", "ativo"]


class LocalLista(AreaMixin, ListView):
    permission_required = "cozinhas.view_localarmazenamento"
    model = LocalArmazenamento
    template_name = "cozinhas/local_lista.html"

    def get_queryset(self):
        return super().get_queryset().select_related("cozinha").annotate(
            n_lotes=Count("lotes", filter=Q(lotes__quantidade_atual__gt=0)))


class LocalCriar(AreaMixin, FormCozinhaMixin, CreateView):
    permission_required = "cozinhas.add_localarmazenamento"
    model = LocalArmazenamento
    form_class = LocalForm
    template_name = "generico/form.html"
    success_url = reverse_lazy("cozinhas:locais")
    extra_context = {"titulo": "Novo local de armazenamento", "voltar": "cozinhas:locais"}

    def form_valid(self, form):
        messages.success(self.request, "Local cadastrado.")
        return super().form_valid(form)


class LocalEditar(AreaMixin, FormCozinhaMixin, UpdateView):
    permission_required = "cozinhas.change_localarmazenamento"
    model = LocalArmazenamento
    form_class = LocalForm
    template_name = "generico/form.html"
    success_url = reverse_lazy("cozinhas:locais")
    extra_context = {"titulo": "Editar local de armazenamento", "voltar": "cozinhas:locais"}

    def form_valid(self, form):
        messages.success(self.request, "Local atualizado.")
        return super().form_valid(form)


class LocalExcluir(AreaMixin, ExclusaoProtegidaMixin, DeleteView):
    permission_required = "cozinhas.delete_localarmazenamento"
    model = LocalArmazenamento
    template_name = "generico/confirmar_exclusao.html"
    success_url = reverse_lazy("cozinhas:locais")
