from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class Usuario(AbstractUser):
    """Usuário do sistema com perfil de acesso e cozinha em que trabalha.

    O perfil define o grupo de permissões (veja contas/perfis.py):
    - Administrador: acesso total ao admin, a todas as cozinhas.
    - Gestor: acessa o admin, mas só enxerga os dados da própria cozinha.
    - Operador: não acessa o admin; usa a área do usuário para registrar
      entradas e saídas (Checkpoint 2).
    """

    class Perfil(models.TextChoices):
        ADMINISTRADOR = "ADMIN", "Administrador"
        GESTOR = "GESTOR", "Gestor"
        OPERADOR = "OPERADOR", "Operador"

    perfil = models.CharField(
        "perfil", max_length=10, choices=Perfil.choices, default=Perfil.OPERADOR)
    cozinha = models.ForeignKey(
        "cozinhas.Cozinha", verbose_name="cozinha", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="usuarios",
        help_text="Obrigatória para gestores e operadores.")
    telefone = models.CharField("telefone", max_length=20, blank=True)

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        ordering = ["first_name", "username"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def eh_administrador(self):
        return self.is_superuser or self.perfil == self.Perfil.ADMINISTRADOR

    def clean(self):
        super().clean()
        if self.perfil != self.Perfil.ADMINISTRADOR and not self.cozinha_id \
                and not self.is_superuser:
            raise ValidationError({"cozinha": "Gestores e operadores precisam de uma cozinha."})

    def save(self, *args, **kwargs):
        # Superusuário criado pelo createsuperuser vira Administrador
        if self.is_superuser:
            self.perfil = self.Perfil.ADMINISTRADOR
        # Só Administrador e Gestor entram no ambiente administrativo
        self.is_staff = self.perfil in (self.Perfil.ADMINISTRADOR, self.Perfil.GESTOR)
        super().save(*args, **kwargs)
        from apps.contas.perfis import sincronizar_grupo
        sincronizar_grupo(self)
