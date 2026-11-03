import re
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

ZERO = Decimal("0")
QTD = {"max_digits": 10, "decimal_places": 3}


def hoje():
    return timezone.localdate()


def limite_alerta():
    return hoje() + timedelta(days=settings.DIAS_ALERTA_VALIDADE)


# ---------------------------------------------------------------------------
# Cadastros básicos
# ---------------------------------------------------------------------------
class Categoria(models.Model):
    nome = models.CharField("nome", max_length=60, unique=True)
    descricao = models.CharField("descrição", max_length=200, blank=True)
    cor = models.CharField("cor", max_length=7, default="#6b8e23",
                           help_text="Cor em hexadecimal usada nos painéis.")
    ativo = models.BooleanField("ativa", default=True)

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def clean(self):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", self.cor or ""):
            raise ValidationError({"cor": "Use o formato #RRGGBB."})
        # RF005/RN02: categoria com produtos ativos não pode ser desativada
        if self.pk and not self.ativo and self.produtos.filter(ativo=True).exists():
            raise ValidationError("Há produtos ativos nesta categoria; não é possível desativá-la.")


class Fornecedor(models.Model):
    nome = models.CharField("nome", max_length=80, unique=True)
    cnpj = models.CharField("CNPJ", max_length=18, unique=True, null=True, blank=True,
                            help_text="Formato 00.000.000/0000-00")
    telefone = models.CharField("telefone", max_length=20, blank=True)
    email = models.EmailField("e-mail", blank=True)
    categorias = models.ManyToManyField(Categoria, verbose_name="categorias que fornece",
                                        blank=True, related_name="fornecedores")
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "fornecedor"
        verbose_name_plural = "fornecedores"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def clean(self):
        if self.cnpj == "":
            self.cnpj = None
        if self.cnpj and not re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", self.cnpj):
            raise ValidationError({"cnpj": "Use o formato 00.000.000/0000-00."})


# ---------------------------------------------------------------------------
# Produto
# ---------------------------------------------------------------------------
class ProdutoQuerySet(models.QuerySet):
    def com_saldo(self):
        """Anota o saldo (soma dos lotes) e o nível de estoque de cada produto."""
        saldo = Coalesce(Sum("lotes__quantidade_atual"), Value(ZERO),
                         output_field=DecimalField(**QTD))
        return self.annotate(saldo=saldo).annotate(
            nivel=Case(
                When(saldo=0, then=Value("ZERADO")),
                When(saldo__lte=F("estoque_minimo"), then=Value("BAIXO")),
                default=Value("OK"),
            ))

    def abaixo_do_minimo(self):
        return self.com_saldo().filter(ativo=True, saldo__lte=F("estoque_minimo"))


class Produto(models.Model):
    class Unidade(models.TextChoices):   # RF006/RN03
        UNIDADE = "un", "unidade (un)"
        QUILO = "kg", "quilograma (kg)"
        GRAMA = "g", "grama (g)"
        LITRO = "l", "litro (l)"
        MILILITRO = "ml", "mililitro (ml)"

    cozinha = models.ForeignKey("cozinhas.Cozinha", verbose_name="cozinha",
                                on_delete=models.PROTECT, related_name="produtos")
    nome = models.CharField("nome", max_length=100)
    categoria = models.ForeignKey(Categoria, verbose_name="categoria", on_delete=models.PROTECT,
                                  related_name="produtos", limit_choices_to={"ativo": True})
    fornecedor_padrao = models.ForeignKey(
        Fornecedor, verbose_name="fornecedor padrão", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="produtos", limit_choices_to={"ativo": True})
    unidade = models.CharField("unidade", max_length=2, choices=Unidade.choices,
                               default=Unidade.UNIDADE)
    estoque_minimo = models.DecimalField("estoque mínimo", default=ZERO,
                                         validators=[MinValueValidator(ZERO)], **QTD)
    perecivel = models.BooleanField("perecível", default=True,
                                    help_text="Perecíveis exigem data de validade nos lotes.")
    codigo_barras = models.CharField("código de barras", max_length=14, blank=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_por = models.ForeignKey("contas.Usuario", verbose_name="criado por",
                                   on_delete=models.PROTECT, related_name="produtos_criados",
                                   null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    objects = ProdutoQuerySet.as_manager()

    class Meta:
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(fields=["cozinha", "nome"],
                                    name="uq_produto_nome_por_cozinha"),
            models.CheckConstraint(condition=Q(estoque_minimo__gte=0),
                                   name="ck_produto_estoque_minimo_positivo"),
        ]

    def __str__(self):
        return f"{self.nome} ({self.unidade})"

    @property
    def saldo_atual(self):
        """Saldo atual = soma das quantidades restantes dos lotes (RF007/RN01)."""
        if hasattr(self, "saldo"):
            return self.saldo
        return self.lotes.aggregate(t=Sum("quantidade_atual"))["t"] or ZERO


# ---------------------------------------------------------------------------
# Lote: cada entrada de mercadoria, com validade e local próprios
# ---------------------------------------------------------------------------
class LoteQuerySet(models.QuerySet):
    def com_saldo(self):
        return self.filter(quantidade_atual__gt=0)

    def vencidos(self):
        return self.com_saldo().filter(data_validade__lt=hoje())

    def vencendo(self):
        return self.com_saldo().filter(data_validade__gte=hoje(),
                                       data_validade__lte=limite_alerta())

    def em_risco(self):
        """RF015: lotes com saldo vencidos ou que vencem dentro do limiar."""
        return self.com_saldo().filter(data_validade__lte=limite_alerta())


class Lote(models.Model):
    produto = models.ForeignKey(Produto, verbose_name="produto", on_delete=models.PROTECT,
                                related_name="lotes", limit_choices_to={"ativo": True})
    local = models.ForeignKey("cozinhas.LocalArmazenamento", verbose_name="local",
                              on_delete=models.PROTECT, related_name="lotes",
                              limit_choices_to={"ativo": True})
    fornecedor = models.ForeignKey(Fornecedor, verbose_name="fornecedor",
                                   on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="lotes")
    codigo = models.CharField("código do lote", max_length=40, blank=True)
    quantidade_inicial = models.DecimalField(
        "quantidade recebida", validators=[MinValueValidator(Decimal("0.001"))], **QTD)
    quantidade_atual = models.DecimalField("quantidade restante", default=ZERO, **QTD)
    data_entrada = models.DateField("data de entrada", default=hoje)
    data_validade = models.DateField("validade", null=True, blank=True)
    custo_unitario = models.DecimalField("custo unitário (R$)", max_digits=10,
                                         decimal_places=2, null=True, blank=True,
                                         validators=[MinValueValidator(ZERO)])
    registrado_por = models.ForeignKey("contas.Usuario", verbose_name="registrado por",
                                       on_delete=models.PROTECT, related_name="lotes",
                                       null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    objects = LoteQuerySet.as_manager()

    class Meta:
        verbose_name = "lote"
        verbose_name_plural = "lotes"
        ordering = ["data_validade", "data_entrada"]
        constraints = [
            models.CheckConstraint(condition=Q(quantidade_atual__gte=0),
                                   name="ck_lote_quantidade_nao_negativa"),
            models.CheckConstraint(condition=Q(quantidade_atual__lte=F("quantidade_inicial")),
                                   name="ck_lote_atual_ate_inicial"),
        ]

    def __str__(self):
        validade = self.data_validade.strftime("%d/%m/%Y") if self.data_validade else "sem validade"
        return f"{self.produto.nome} · {self.codigo or f'lote {self.pk}'} · {validade}"

    @property
    def situacao(self):
        if self.quantidade_atual <= 0:
            return "ESGOTADO"
        if self.data_validade is None:
            return "OK"
        if self.data_validade < hoje():
            return "VENCIDO"
        if self.data_validade <= limite_alerta():
            return "VENCENDO"
        return "OK"

    @property
    def dias_para_vencer(self):
        return (self.data_validade - hoje()).days if self.data_validade else None

    @property
    def valor_em_estoque(self):
        return (self.custo_unitario or ZERO) * self.quantidade_atual

    def clean(self):
        erros = {}
        if self.data_entrada and self.data_entrada > hoje():
            erros["data_entrada"] = "A data de entrada não pode ser futura."   # RF010/RN02
        if self.produto_id and self.produto.perecivel and not self.data_validade:
            erros["data_validade"] = "Produtos perecíveis exigem data de validade."
        if self.data_validade and self.data_entrada and self.data_validade < self.data_entrada:
            erros["data_validade"] = "A validade não pode ser anterior à entrada."
        if self.produto_id and self.local_id and self.local.cozinha_id != self.produto.cozinha_id:
            erros["local"] = "O local precisa ser da mesma cozinha do produto."
        if erros:
            raise ValidationError(erros)


# ---------------------------------------------------------------------------
# Movimentação: histórico imutável de tudo que entra e sai
# ---------------------------------------------------------------------------
class Movimentacao(models.Model):
    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SAIDA = "SAIDA", "Saída (consumo)"
        DESCARTE = "DESCARTE", "Descarte"

    class Motivo(models.TextChoices):
        COMPRA = "COMPRA", "Compra / recebimento"
        DOACAO = "DOACAO", "Doação recebida"
        PREPARO = "PREPARO", "Preparo de refeição"
        VENCIMENTO = "VENCIMENTO", "Produto vencido"
        AVARIA = "AVARIA", "Avaria / estragado"
        OUTRO = "OUTRO", "Outro"

    lote = models.ForeignKey(Lote, verbose_name="lote", on_delete=models.PROTECT,
                             related_name="movimentacoes")
    tipo = models.CharField("tipo", max_length=8, choices=Tipo.choices)
    motivo = models.CharField("motivo", max_length=10, choices=Motivo.choices,
                              default=Motivo.OUTRO)
    quantidade = models.DecimalField("quantidade",
                                     validators=[MinValueValidator(Decimal("0.001"))], **QTD)
    data = models.DateField("data", default=hoje)
    usuario = models.ForeignKey("contas.Usuario", verbose_name="responsável",
                                on_delete=models.PROTECT, related_name="movimentacoes")
    observacao = models.CharField("observação", max_length=200, blank=True)
    criado_em = models.DateTimeField("registrado em", auto_now_add=True)

    class Meta:
        verbose_name = "movimentação"
        verbose_name_plural = "movimentações"
        ordering = ["-data", "-criado_em"]
        constraints = [
            models.CheckConstraint(condition=Q(quantidade__gt=0),
                                   name="ck_movimentacao_quantidade_positiva"),
        ]
        indexes = [models.Index(fields=["data", "tipo"])]

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.quantidade} {self.lote.produto.unidade} " \
               f"– {self.lote.produto.nome}"

    @property
    def produto(self):
        return self.lote.produto

    @property
    def sinal(self):
        return 1 if self.tipo == self.Tipo.ENTRADA else -1
