from django.core.exceptions import ValidationError
from django.db import models


class Cozinha(models.Model):
    """Unidade que tem estoque próprio: uma casa, um restaurante, um refeitório."""

    class Tipo(models.TextChoices):
        DOMESTICA = "DOMESTICA", "Doméstica"
        INSTITUCIONAL = "INSTITUCIONAL", "Institucional"
        COMERCIAL = "COMERCIAL", "Comercial"

    nome = models.CharField("nome", max_length=80, unique=True)
    tipo = models.CharField("tipo", max_length=15, choices=Tipo.choices,
                            default=Tipo.DOMESTICA)
    endereco = models.CharField("endereço", max_length=200, blank=True)
    cidade = models.CharField("cidade", max_length=80, blank=True)
    refeicoes_por_dia = models.PositiveIntegerField(
        "refeições por dia", default=0,
        help_text="Estimativa usada para dimensionar as compras.")
    responsavel = models.ForeignKey(
        "contas.Usuario", verbose_name="responsável", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="cozinhas_responsavel")
    ativa = models.BooleanField("ativa", default=True)
    criada_em = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "cozinha"
        verbose_name_plural = "cozinhas"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class LocalArmazenamento(models.Model):
    """Onde os lotes ficam guardados: despensa, geladeira, freezer..."""

    class Tipo(models.TextChoices):
        DESPENSA = "DESPENSA", "Despensa (temperatura ambiente)"
        GELADEIRA = "GELADEIRA", "Geladeira"
        FREEZER = "FREEZER", "Freezer"
        CAMARA_FRIA = "CAMARA_FRIA", "Câmara fria"

    cozinha = models.ForeignKey(Cozinha, verbose_name="cozinha", on_delete=models.CASCADE,
                                related_name="locais")
    nome = models.CharField("nome", max_length=60)
    tipo = models.CharField("tipo", max_length=12, choices=Tipo.choices,
                            default=Tipo.DESPENSA)
    temperatura_min = models.DecimalField("temperatura mínima (°C)", max_digits=4,
                                          decimal_places=1, null=True, blank=True)
    temperatura_max = models.DecimalField("temperatura máxima (°C)", max_digits=4,
                                          decimal_places=1, null=True, blank=True)
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "local de armazenamento"
        verbose_name_plural = "locais de armazenamento"
        ordering = ["cozinha__nome", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["cozinha", "nome"],
                                    name="uq_local_nome_por_cozinha"),
        ]

    def __str__(self):
        return f"{self.nome} ({self.cozinha})"

    def clean(self):
        if (self.temperatura_min is not None and self.temperatura_max is not None
                and self.temperatura_min > self.temperatura_max):
            raise ValidationError("A temperatura mínima não pode ser maior que a máxima.")
