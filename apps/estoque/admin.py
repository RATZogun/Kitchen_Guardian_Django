from collections import defaultdict
from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import (
    BooleanRadioFilter,
    ChoicesCheckboxFilter,
    ChoicesDropdownFilter,
    MultipleRelatedDropdownFilter,
    RangeDateFilter,
    RangeDateTimeFilter,
    RangeNumericFilter,
    RelatedDropdownFilter,
)
from unfold.decorators import display

from apps.compras.models import ItemListaCompra, ListaCompra
from apps.core.admin_mixins import EscopoCozinhaMixin, eh_admin_geral

from . import services
from .filters import ComRiscoFilter, NivelEstoqueFilter, SituacaoValidadeFilter
from .models import Categoria, Fornecedor, Lote, Movimentacao, Produto, hoje, limite_alerta

COR_SITUACAO = {"Vencido": "danger", "Vence em breve": "warning", "OK": "success",
                "Esgotado": "info"}
COR_NIVEL = {"Zerado": "danger", "Baixo": "warning", "OK": "success"}


def qtd(valor, unidade=""):
    """1.500 -> '1,5'; 3.000 -> '3'."""
    texto = f"{valor.normalize():f}" if isinstance(valor, Decimal) else str(valor)
    return f"{texto.replace('.', ',')} {unidade}".strip()


# ---------------------------------------------------------------------------
# Categoria e Fornecedor
# ---------------------------------------------------------------------------
@admin.register(Categoria)
class CategoriaAdmin(ModelAdmin):
    list_display = ["nome", "amostra_cor", "descricao", "total_produtos", "total_fornecedores",
                    "ativo"]
    list_editable = ["ativo"]
    search_fields = ["nome", "descricao"]
    list_filter = [("ativo", BooleanRadioFilter),
                   ("fornecedores", MultipleRelatedDropdownFilter)]
    list_filter_submit = True

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            n_produtos=Count("produtos", filter=Q(produtos__ativo=True), distinct=True),
            n_fornecedores=Count("fornecedores", distinct=True))

    @display(description="cor")
    def amostra_cor(self, obj):
        return format_html('<span style="display:inline-block;width:1.1rem;height:1.1rem;'
                           'border-radius:4px;background:{}"></span>', obj.cor)

    @display(description="produtos ativos", ordering="n_produtos")
    def total_produtos(self, obj):
        return obj.n_produtos

    @display(description="fornecedores", ordering="n_fornecedores")
    def total_fornecedores(self, obj):
        return obj.n_fornecedores


@admin.register(Fornecedor)
class FornecedorAdmin(ModelAdmin):
    list_display = ["nome", "cnpj", "telefone", "email", "lista_categorias", "ativo"]
    search_fields = ["nome", "cnpj", "email"]
    list_filter = [("ativo", BooleanRadioFilter),
                   ("categorias", MultipleRelatedDropdownFilter)]
    list_filter_submit = True
    filter_horizontal = ["categorias"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("categorias")

    @display(description="categorias")
    def lista_categorias(self, obj):
        return ", ".join(c.nome for c in obj.categorias.all()) or "—"


# ---------------------------------------------------------------------------
# Produto
# ---------------------------------------------------------------------------
class LoteInline(TabularInline):
    model = Lote
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ["codigo", "local", "quantidade_atual", "data_validade", "situacao_badge"]
    readonly_fields = fields
    verbose_name_plural = "lotes com saldo"
    tab = True

    def get_queryset(self, request):
        return super().get_queryset(request).filter(quantidade_atual__gt=0)

    def has_add_permission(self, request, obj=None):
        return False   # entradas são registradas em Lotes, para gerar a movimentação

    @display(description="situação", label=COR_SITUACAO)
    def situacao_badge(self, obj):
        return rotulo_situacao(obj)


def rotulo_situacao(lote):
    return {"VENCIDO": "Vencido", "VENCENDO": "Vence em breve", "OK": "OK",
            "ESGOTADO": "Esgotado"}[lote.situacao]


@admin.register(Produto)
class ProdutoAdmin(EscopoCozinhaMixin, ModelAdmin):
    list_display = ["nome", "categoria", "cozinha", "saldo_fmt", "minimo_fmt", "nivel_badge",
                    "lotes_em_risco", "ativo"]
    list_display_links = ["nome"]
    search_fields = ["nome", "codigo_barras", "categoria__nome"]
    autocomplete_fields = ["categoria", "fornecedor_padrao"]
    list_filter = [
        NivelEstoqueFilter,
        ComRiscoFilter,
        ("cozinha", RelatedDropdownFilter),
        ("categoria", RelatedDropdownFilter),
        ("fornecedor_padrao", RelatedDropdownFilter),
        ("unidade", ChoicesDropdownFilter),
        ("perecivel", BooleanRadioFilter),
        ("estoque_minimo", RangeNumericFilter),
        ("criado_em", RangeDateTimeFilter),
        ("ativo", BooleanRadioFilter),
    ]
    list_filter_submit = True
    list_per_page = 25
    readonly_fields = ["saldo_fmt", "criado_por", "criado_em", "atualizado_em"]
    inlines = [LoteInline]
    actions = ["gerar_lista_compras", "desativar"]
    fieldsets = [
        ("Identificação", {"fields": ["cozinha", "nome", "categoria", "codigo_barras", "ativo"]}),
        ("Estoque", {"fields": ["unidade", "estoque_minimo", "saldo_fmt", "perecivel",
                                "fornecedor_padrao"]}),
        ("Auditoria", {"classes": ["collapse"],
                       "fields": ["criado_por", "criado_em", "atualizado_em"]}),
    ]

    def get_queryset(self, request):
        em_risco = Lote.objects.em_risco().filter(produto=OuterRef("pk")) \
            .values("produto").annotate(n=Count("pk")).values("n")
        return super().get_queryset(request).com_saldo().select_related(
            "categoria", "cozinha").annotate(
            n_risco=Coalesce(Subquery(em_risco, output_field=IntegerField()), 0))

    def save_model(self, request, obj, form, change):
        if not change:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)

    @display(description="saldo", ordering="saldo")
    def saldo_fmt(self, obj):
        if not obj.pk:
            return "—"
        return qtd(obj.saldo_atual, obj.unidade)

    @display(description="mínimo", ordering="estoque_minimo")
    def minimo_fmt(self, obj):
        return qtd(obj.estoque_minimo, obj.unidade)

    @display(description="nível", label=COR_NIVEL, ordering="nivel")
    def nivel_badge(self, obj):
        return {"ZERADO": "Zerado", "BAIXO": "Baixo", "OK": "OK"}[obj.nivel]

    @display(description="lotes em risco", ordering="n_risco")
    def lotes_em_risco(self, obj):
        if not obj.n_risco:
            return "—"
        url = reverse("admin:estoque_lote_changelist") + f"?produto__id__exact={obj.pk}&situacao=VENCENDO"
        return format_html('<a href="{}" style="color:#d97706;font-weight:600">{} lote(s)</a>',
                           url, obj.n_risco)

    @admin.action(description="Gerar lista de compras com os selecionados abaixo do mínimo",
                  permissions=["add_lista"])
    def gerar_lista_compras(self, request, queryset):
        """Cria uma lista por cozinha; quantidade sugerida = 2 x mínimo - saldo."""
        por_cozinha = defaultdict(list)
        for produto in queryset.abaixo_do_minimo():
            por_cozinha[produto.cozinha].append(produto)
        if not por_cozinha:
            self.message_user(request, "Nenhum dos produtos selecionados está abaixo do mínimo.",
                              messages.WARNING)
            return
        for cozinha, produtos in por_cozinha.items():
            lista = ListaCompra.objects.create(
                cozinha=cozinha, criada_por=request.user,
                titulo=f"Reposição {hoje():%d/%m/%Y}")
            ItemListaCompra.objects.bulk_create([
                ItemListaCompra(lista=lista, produto=p, fornecedor=p.fornecedor_padrao,
                                quantidade=max(2 * p.estoque_minimo - p.saldo, Decimal("1")))
                for p in produtos])
            url = reverse("admin:compras_listacompra_change", args=[lista.pk])
            self.message_user(request, format_html(
                'Lista <a href="{}">{}</a> criada com {} item(ns).', url, lista, len(produtos)),
                messages.SUCCESS)

    def has_add_lista_permission(self, request):
        return request.user.has_perm("compras.add_listacompra")

    @admin.action(description="Desativar produtos selecionados (exclusão lógica)",
                  permissions=["change"])
    def desativar(self, request, queryset):
        n = queryset.update(ativo=False)
        self.message_user(request, f"{n} produto(s) desativado(s).", messages.SUCCESS)


# ---------------------------------------------------------------------------
# Lote
# ---------------------------------------------------------------------------
class MovimentacaoInline(TabularInline):
    model = Movimentacao
    extra = 0
    can_delete = False
    fields = ["data", "tipo", "motivo", "quantidade", "usuario", "observacao"]
    readonly_fields = fields
    tab = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Lote)
class LoteAdmin(EscopoCozinhaMixin, ModelAdmin):
    campo_cozinha = "produto__cozinha"
    list_display = ["produto", "codigo", "local", "restante_fmt", "data_validade",
                    "situacao_badge", "prazo", "valor_fmt"]
    search_fields = ["produto__nome", "codigo", "fornecedor__nome"]
    autocomplete_fields = ["produto", "fornecedor"]
    list_select_related = ["produto", "local", "local__cozinha"]
    list_filter = [
        SituacaoValidadeFilter,
        ("produto__cozinha", RelatedDropdownFilter),
        ("produto__categoria", RelatedDropdownFilter),
        ("local__tipo", ChoicesDropdownFilter),
        ("fornecedor", RelatedDropdownFilter),
        ("data_validade", RangeDateFilter),
        ("data_entrada", RangeDateFilter),
        ("quantidade_atual", RangeNumericFilter),
    ]
    list_filter_submit = True
    date_hierarchy = "data_validade"
    inlines = [MovimentacaoInline]
    actions = ["descartar_vencidos"]

    def get_fieldsets(self, request, obj=None):
        entrada = ["produto", "local", "fornecedor", "codigo", "quantidade_inicial",
                   "data_entrada", "data_validade", "custo_unitario"]
        if obj is None:
            return [("Entrada de mercadoria", {
                "fields": entrada,
                "description": "Salvar o lote registra automaticamente a movimentação de "
                               "entrada no seu nome."})]
        return [("Lote", {"fields": entrada}),
                ("Saldo", {"fields": ["quantidade_atual", "situacao_badge", "valor_fmt",
                                      "registrado_por", "criado_em"]})]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        # depois de registrado, só dados descritivos podem mudar; o saldo muda via movimentações
        return ["produto", "quantidade_inicial", "data_entrada", "quantidade_atual",
                "situacao_badge", "valor_fmt", "registrado_por", "criado_em"]

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
        else:
            services.registrar_entrada(obj, request.user)

    def has_delete_permission(self, request, obj=None):
        return False   # lotes têm histórico; esgote-os com movimentações

    @display(description="restante", ordering="quantidade_atual")
    def restante_fmt(self, obj):
        return f"{qtd(obj.quantidade_atual)} / {qtd(obj.quantidade_inicial, obj.produto.unidade)}"

    @display(description="situação", label=COR_SITUACAO)
    def situacao_badge(self, obj):
        return rotulo_situacao(obj)

    @display(description="prazo", ordering="data_validade")
    def prazo(self, obj):
        dias = obj.dias_para_vencer
        if dias is None or obj.quantidade_atual == 0:
            return "—"
        if dias < 0:
            return f"vencido há {-dias} dia(s)"
        return "vence hoje" if dias == 0 else f"{dias} dia(s)"

    @display(description="valor em estoque")
    def valor_fmt(self, obj):
        return f"R$ {obj.valor_em_estoque:.2f}".replace(".", ",")

    @admin.action(description="Descartar saldo dos lotes vencidos selecionados",
                  permissions=["change"])
    def descartar_vencidos(self, request, queryset):
        n = services.descartar_vencidos(queryset, request.user)
        nivel = messages.SUCCESS if n else messages.WARNING
        self.message_user(request, f"{n} lote(s) vencido(s) descartado(s).", nivel)


# ---------------------------------------------------------------------------
# Movimentação (somente inclusão: o histórico é imutável)
# ---------------------------------------------------------------------------
class BaixaForm(forms.ModelForm):
    class Meta:
        model = Movimentacao
        fields = ["lote", "tipo", "motivo", "quantidade", "data", "observacao"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo"].choices = [c for c in Movimentacao.Tipo.choices
                                       if c[0] != Movimentacao.Tipo.ENTRADA]
        self.fields["lote"].queryset = self.fields["lote"].queryset.filter(
            quantidade_atual__gt=0).select_related("produto")
        self.fields["lote"].help_text = "Entradas são registradas cadastrando um novo lote."

    def clean(self):
        dados = super().clean()
        lote, quantidade, data = dados.get("lote"), dados.get("quantidade"), dados.get("data")
        if lote and quantidade and quantidade > lote.quantidade_atual:
            self.add_error("quantidade", f"Saldo insuficiente: restam "
                                         f"{qtd(lote.quantidade_atual, lote.produto.unidade)}.")
        if data and data > hoje():
            self.add_error("data", "A data não pode ser futura.")
        return dados


@admin.register(Movimentacao)
class MovimentacaoAdmin(EscopoCozinhaMixin, ModelAdmin):
    campo_cozinha = "lote__produto__cozinha"
    form = BaixaForm
    list_display = ["data", "tipo_badge", "produto_link", "quantidade_fmt", "motivo",
                    "usuario", "observacao"]
    search_fields = ["lote__produto__nome", "lote__codigo", "usuario__username",
                     "usuario__first_name", "observacao"]
    list_select_related = ["lote__produto", "usuario"]
    list_filter = [
        ("tipo", ChoicesCheckboxFilter),
        ("motivo", ChoicesDropdownFilter),
        ("data", RangeDateFilter),
        ("usuario", RelatedDropdownFilter),
        ("lote__produto__cozinha", RelatedDropdownFilter),
        ("lote__produto__categoria", RelatedDropdownFilter),
        ("quantidade", RangeNumericFilter),
    ]
    list_filter_submit = True
    date_hierarchy = "data"
    autocomplete_fields = ["lote"]

    def save_model(self, request, obj, form, change):
        try:
            nova = services.registrar_baixa(
                obj.lote, obj.quantidade, request.user, tipo=obj.tipo, motivo=obj.motivo,
                data=obj.data, observacao=obj.observacao)
        except ValidationError as erro:   # corrida rara: o saldo mudou após validar o form
            self.message_user(request, "; ".join(erro.messages), messages.ERROR)
            return
        obj.pk = nova.pk

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description="tipo", ordering="tipo",
             label={"Entrada": "success", "Saída (consumo)": "info", "Descarte": "danger"})
    def tipo_badge(self, obj):
        return obj.get_tipo_display()

    @display(description="produto", ordering="lote__produto__nome")
    def produto_link(self, obj):
        url = reverse("admin:estoque_lote_change", args=[obj.lote_id])
        return format_html('<a href="{}">{}</a>', url, obj.lote.produto.nome)

    @display(description="quantidade", ordering="quantidade")
    def quantidade_fmt(self, obj):
        sinal = "+" if obj.tipo == Movimentacao.Tipo.ENTRADA else "−"
        return f"{sinal}{qtd(obj.quantidade, obj.lote.produto.unidade)}"
