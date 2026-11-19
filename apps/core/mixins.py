"""Controle de acesso da área do usuário.

Mesma regra do admin (admin_mixins.py): o Administrador vê todas as cozinhas;
Gestor e Operador veem apenas a própria. As ações permitidas a cada perfil
vêm das permissões dos grupos (contas/perfis.py).
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.shortcuts import redirect

from apps.core.admin_mixins import CAMINHO_COZINHA


def eh_admin_geral(user):
    return user.is_superuser or getattr(user, "eh_administrador", False)


def escopo(user, qs, caminho="cozinha"):
    """Filtra o queryset pela cozinha do usuário, exceto para o Administrador."""
    if eh_admin_geral(user):
        return qs
    return qs.filter(**{caminho: user.cozinha_id})


def restringir_campos(form, user):
    """Limita as opções de chave estrangeira do formulário à cozinha do usuário."""
    if eh_admin_geral(user):
        return form
    for campo in form.fields.values():
        qs = getattr(campo, "queryset", None)
        if qs is None:
            continue
        caminho = CAMINHO_COZINHA.get(qs.model._meta.model_name)
        if caminho:
            campo.queryset = qs.filter(**{caminho: user.cozinha_id})
    return form


class AreaMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Exige login e a permissão da view; aplica o escopo da cozinha nas consultas."""

    #: lookup do modelo até a cozinha (ex.: "produto__cozinha")
    campo_cozinha = "cozinha"

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "Seu perfil não tem permissão para essa ação.")
            return redirect("core:painel")
        return super().handle_no_permission()

    def get_queryset(self):
        return escopo(self.request.user, super().get_queryset(), self.campo_cozinha)


class FormCozinhaMixin:
    """Formulários de criação/edição: escopo nos campos e cozinha preenchida sozinha."""

    def get_form(self, form_class=None):
        form = restringir_campos(super().get_form(form_class), self.request.user)
        if "cozinha" in form.fields and not eh_admin_geral(self.request.user):
            # a cozinha vem do usuário, antes da validação do formulário
            del form.fields["cozinha"]
            form.instance.cozinha_id = self.request.user.cozinha_id
        return form

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ValidationError as erro:
            form.add_error(None, erro)
            return self.form_invalid(form)


class ExclusaoProtegidaMixin:
    """Mostra uma mensagem amigável quando o registro tem dependentes (on_delete=PROTECT)."""

    def form_valid(self, form):
        try:
            resposta = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, "Não é possível excluir: há registros que dependem deste. "
                                         "Desative-o em vez de excluir.")
            return redirect(self.get_success_url())
        messages.success(self.request, "Registro excluído.")
        return resposta
