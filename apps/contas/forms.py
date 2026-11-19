from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.db import transaction

from apps.core.forms import BootstrapMixin
from apps.cozinhas.models import Cozinha, LocalArmazenamento

from .models import Usuario

# Locais criados junto com a cozinha de quem se cadastra
LOCAIS_PADRAO = [
    ("Despensa", LocalArmazenamento.Tipo.DESPENSA, None, None),
    ("Geladeira", LocalArmazenamento.Tipo.GELADEIRA, 2, 6),
    ("Freezer", LocalArmazenamento.Tipo.FREEZER, -22, -16),
]


class LoginForm(BootstrapMixin, AuthenticationForm):
    error_messages = {
        "invalid_login": "Usuário ou senha incorretos.",
        "inactive": "Esta conta está desativada.",
    }


class CadastroForm(BootstrapMixin, UserCreationForm):
    """Cadastre-se: cria a conta e a cozinha da pessoa, que vira Gestora dela."""

    nome_cozinha = forms.CharField(label="Nome da sua cozinha", max_length=80,
                                   help_text="Ex.: Casa da Ana, Cantina do Bloco 3.")
    tipo_cozinha = forms.ChoiceField(label="Tipo de cozinha", choices=Cozinha.Tipo.choices)
    cidade = forms.CharField(label="Cidade", max_length=80, required=False)

    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ["first_name", "last_name", "username", "email"]
        labels = {"first_name": "Nome", "last_name": "Sobrenome", "email": "E-mail"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["email"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email

    def clean_nome_cozinha(self):
        nome = self.cleaned_data["nome_cozinha"].strip()
        if Cozinha.objects.filter(nome__iexact=nome).exists():
            raise forms.ValidationError("Já existe uma cozinha com este nome.")
        return nome

    def _post_clean(self):
        # A cozinha só é criada no save(); sem isto, Usuario.clean() recusaria o gestor
        # "sem cozinha" durante a validação do formulário.
        self.instance.perfil = Usuario.Perfil.ADMINISTRADOR
        super()._post_clean()
        self.instance.perfil = Usuario.Perfil.GESTOR

    @transaction.atomic
    def save(self, commit=True):
        cozinha = Cozinha.objects.create(
            nome=self.cleaned_data["nome_cozinha"], tipo=self.cleaned_data["tipo_cozinha"],
            cidade=self.cleaned_data.get("cidade", ""))
        for nome, tipo, tmin, tmax in LOCAIS_PADRAO:
            LocalArmazenamento.objects.create(cozinha=cozinha, nome=nome, tipo=tipo,
                                              temperatura_min=tmin, temperatura_max=tmax)
        usuario = super().save(commit=False)
        usuario.perfil = Usuario.Perfil.GESTOR
        usuario.cozinha = cozinha
        usuario.save()
        cozinha.responsavel = usuario
        cozinha.save(update_fields=["responsavel"])
        return usuario


class PerfilForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "email", "telefone"]
        labels = {"first_name": "Nome", "last_name": "Sobrenome", "email": "E-mail"}

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if email and Usuario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email


class SenhaForm(BootstrapMixin, PasswordChangeForm):
    pass
