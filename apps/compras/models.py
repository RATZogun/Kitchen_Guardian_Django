from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

QTD = {"max_digits": 10, "decimal_places": 3}


class ListaCompra(models.Model):
    """Lista de reposição de uma cozinha, gerada à mão ou a partir do estoque baixo."""

    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        ENVIADA = "ENVIADA", "Enviada ao fornecedor"
        CONCLUIDA = "CONCLUIDA", "Concluída"
        CANCELADA = "CANCELADA", "Cancelada"

    cozinha = models.ForeignKey("cozinhas.Cozinha", verbose_name="cozinha",
                                on_delete=models.CASCADE, related_name="listas_compra")
    titulo = models.CharField("título", max_length=100)
    status = models.CharField("status", max_length=10, choices=Status.choices,
                              default=Status.RASCUNHO)
    data_prevista = models.DateField("compra prevista para", null=True, blank=True)
    observacoes = models.TextField("observações", blank=True)
    criada_por = models.ForeignKey("contas.Usuario", verbose_name="criada por",
                                   on_delete=models.PROTECT, related_name="listas_compra",
                                   null=True, blank=True)
    criada_em = models.DateTimeField("criada em", auto_now_add=True)
    concluida_em = models.DateTimeField("concluída em", null=True, blank=True)

    class Meta:
        verbose_name = "lista de compras"
        verbose_name_plural = "listas de compras"
        ordering = ["-criada_em"]

    def __str__(self):
        return f"{self.titulo} ({self.cozinha})"

    @property
    def total_estimado(self):
        total = self.itens.aggregate(t=Sum(ExpressionWrapper(
            F("quantidade") * F("preco_estimado"),
            output_field=DecimalField(max_digits=14, decimal_places=2))))["t"]
        return total or Decimal("0")

    @property
    def progresso(self):
        """Percentual de itens já comprados."""
        total = self.itens.count()
        return round(100 * self.itens.filter(comprado=True).count() / total) if total else 0

    def save(self, *args, **kwargs):
        if self.status == self.Status.CONCLUIDA and not self.concluida_em:
            self.concluida_em = timezone.now()
        super().save(*args, **kwargs)


class ItemListaCompra(models.Model):
    lista = models.ForeignKey(ListaCompra, verbose_name="lista", on_delete=models.CASCADE,
                              related_name="itens")
    produto = models.ForeignKey("estoque.Produto", verbose_name="produto",
                                on_delete=models.PROTECT, related_name="itens_compra")
    quantidade = models.DecimalField("quantidade", validators=[MinValueValidator(Decimal("0.001"))],
                                     **QTD)
    fornecedor = models.ForeignKey("estoque.Fornecedor", verbose_name="fornecedor",
                                   on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="itens_compra")
    preco_estimado = models.DecimalField("preço unitário estimado (R$)", max_digits=10,
                                         decimal_places=2, default=Decimal("0"),
                                         validators=[MinValueValidator(Decimal("0"))])
    comprado = models.BooleanField("comprado", default=False)

    class Meta:
        verbose_name = "item da lista"
        verbose_name_plural = "itens da lista"
        ordering = ["produto__nome"]
        constraints = [
            models.UniqueConstraint(fields=["lista", "produto"], name="uq_item_produto_por_lista"),
        ]

    def __str__(self):
        return f"{self.quantidade} {self.produto.unidade} de {self.produto.nome}"

    @property
    def subtotal(self):
        return self.quantidade * self.preco_estimado

    def clean(self):
        if self.lista_id and self.produto_id and \
                self.produto.cozinha_id != self.lista.cozinha_id:
            raise ValidationError({"produto": "O produto precisa ser da mesma cozinha da lista."})
