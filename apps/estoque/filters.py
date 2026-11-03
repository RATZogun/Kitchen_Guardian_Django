"""Filtros personalizados do admin do estoque."""
from django.contrib import admin
from django.db.models import F

from .models import hoje, limite_alerta


class NivelEstoqueFilter(admin.SimpleListFilter):
    """RF013/RN02: baixo estoque = saldo <= estoque mínimo."""
    title = "nível de estoque"
    parameter_name = "nivel"

    def lookups(self, request, model_admin):
        return [("ZERADO", "Zerado"), ("BAIXO", "Abaixo do mínimo (inclui zerado)"),
                ("OK", "Acima do mínimo")]

    def queryset(self, request, queryset):
        # o queryset do ProdutoAdmin já vem anotado com "saldo"
        if self.value() == "ZERADO":
            return queryset.filter(saldo=0)
        if self.value() == "BAIXO":
            return queryset.filter(saldo__lte=F("estoque_minimo"))
        if self.value() == "OK":
            return queryset.filter(saldo__gt=F("estoque_minimo"))
        return queryset


class SituacaoValidadeFilter(admin.SimpleListFilter):
    """RF015: situação do lote em relação à validade."""
    title = "situação da validade"
    parameter_name = "situacao"

    def lookups(self, request, model_admin):
        return [("VENCIDO", "Vencido (com saldo)"), ("VENCENDO", "Vence em até 7 dias"),
                ("OK", "Dentro da validade"), ("SEM", "Sem validade"),
                ("ESGOTADO", "Esgotado")]

    def queryset(self, request, queryset):
        valor = self.value()
        com_saldo = queryset.filter(quantidade_atual__gt=0)
        if valor == "VENCIDO":
            return com_saldo.filter(data_validade__lt=hoje())
        if valor == "VENCENDO":
            return com_saldo.filter(data_validade__gte=hoje(), data_validade__lte=limite_alerta())
        if valor == "OK":
            return com_saldo.filter(data_validade__gt=limite_alerta())
        if valor == "SEM":
            return com_saldo.filter(data_validade__isnull=True)
        if valor == "ESGOTADO":
            return queryset.filter(quantidade_atual=0)
        return queryset


class ComRiscoFilter(admin.SimpleListFilter):
    """Produtos que têm algum lote vencido ou vencendo."""
    title = "risco de validade"
    parameter_name = "risco"

    def lookups(self, request, model_admin):
        return [("SIM", "Com lotes em risco"), ("NAO", "Sem lotes em risco")]

    def queryset(self, request, queryset):
        # subconsulta (e não join) para não multiplicar a soma do saldo anotada no queryset
        em_risco = queryset.model.objects.filter(
            lotes__quantidade_atual__gt=0, lotes__data_validade__lte=limite_alerta()).values("pk")
        if self.value() == "SIM":
            return queryset.filter(pk__in=em_risco)
        if self.value() == "NAO":
            return queryset.exclude(pk__in=em_risco)
        return queryset
