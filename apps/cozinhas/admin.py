from django.contrib import admin
from django.db.models import Count, Q
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import (
    AllValuesCheckboxFilter,
    BooleanRadioFilter,
    ChoicesCheckboxFilter,
    ChoicesDropdownFilter,
    RangeNumericFilter,
    RelatedDropdownFilter,
)
from unfold.decorators import display

from apps.core.admin_mixins import EscopoCozinhaMixin

from .models import Cozinha, LocalArmazenamento


class LocalInline(TabularInline):
    model = LocalArmazenamento
    extra = 0
    fields = ["nome", "tipo", "temperatura_min", "temperatura_max", "ativo"]
    tab = True


@admin.register(Cozinha)
class CozinhaAdmin(EscopoCozinhaMixin, ModelAdmin):
    campo_cozinha = "pk"
    list_display = ["nome", "tipo_badge", "cidade", "responsavel", "refeicoes_por_dia",
                    "total_locais", "total_produtos", "total_usuarios", "ativa"]
    search_fields = ["nome", "cidade", "endereco"]
    list_filter = [
        ("tipo", ChoicesCheckboxFilter),
        ("cidade", AllValuesCheckboxFilter),
        ("refeicoes_por_dia", RangeNumericFilter),
        ("ativa", BooleanRadioFilter),
    ]
    list_filter_submit = True
    autocomplete_fields = ["responsavel"]
    inlines = [LocalInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("responsavel").annotate(
            n_locais=Count("locais", distinct=True),
            n_produtos=Count("produtos", filter=Q(produtos__ativo=True), distinct=True),
            n_usuarios=Count("usuarios", distinct=True))

    @display(description="tipo", ordering="tipo",
             label={"Doméstica": "info", "Institucional": "primary", "Comercial": "warning"})
    def tipo_badge(self, obj):
        return obj.get_tipo_display()

    @display(description="locais", ordering="n_locais")
    def total_locais(self, obj):
        return obj.n_locais

    @display(description="produtos ativos", ordering="n_produtos")
    def total_produtos(self, obj):
        return obj.n_produtos

    @display(description="usuários", ordering="n_usuarios")
    def total_usuarios(self, obj):
        return obj.n_usuarios


@admin.register(LocalArmazenamento)
class LocalArmazenamentoAdmin(EscopoCozinhaMixin, ModelAdmin):
    list_display = ["nome", "cozinha", "tipo", "faixa_temperatura", "lotes_com_saldo", "ativo"]
    search_fields = ["nome", "cozinha__nome"]
    list_filter = [
        ("cozinha", RelatedDropdownFilter),
        ("tipo", ChoicesDropdownFilter),
        ("ativo", BooleanRadioFilter),
    ]
    list_filter_submit = True

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("cozinha").annotate(
            n_lotes=Count("lotes", filter=Q(lotes__quantidade_atual__gt=0)))

    @display(description="temperatura")
    def faixa_temperatura(self, obj):
        if obj.temperatura_min is None and obj.temperatura_max is None:
            return "ambiente"
        return f"{obj.temperatura_min} a {obj.temperatura_max} °C"

    @display(description="lotes com saldo", ordering="n_lotes")
    def lotes_com_saldo(self, obj):
        return obj.n_lotes
