from django.contrib import admin, messages
from django.db.models import Count, Q
from django.forms.models import BaseInlineFormSet
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import (
    ChoicesCheckboxFilter,
    RangeDateFilter,
    RangeDateTimeFilter,
    RelatedDropdownFilter,
)
from unfold.decorators import display

from apps.core.admin_mixins import EscopoCozinhaMixin, ve_todas_as_cozinhas
from apps.estoque.models import Produto

from .models import ItemListaCompra, ListaCompra

COR_STATUS = {"Rascunho": "info", "Enviada ao fornecedor": "warning", "Concluída": "success",
              "Cancelada": "danger"}


class ItensInlineFormSet(BaseInlineFormSet):
    """Produtos dos itens limitados à cozinha da lista.

    - Lista nova (sem cozinha ainda): usa a cozinha do usuário; o Administrador vê todos e a
      cozinha é conferida no POST, quando a lista já recebeu a cozinha escolhida.
    - O produto atual do item continua disponível mesmo se tiver sido desativado depois.
    """

    #: preenchido por ItemInline.get_formset com o usuário da requisição
    usuario = None

    def _cozinha_id(self):
        if self.instance.cozinha_id:
            return self.instance.cozinha_id
        if self.usuario is not None and not ve_todas_as_cozinhas(self.usuario):
            return self.usuario.cozinha_id
        return None

    def add_fields(self, form, index):
        # chamado para cada formulário, inclusive o modelo vazio do "adicionar outro item"
        super().add_fields(form, index)
        if "produto" not in form.fields:
            return
        produtos = Produto.objects.select_related("cozinha").order_by("nome")
        cozinha_id = self._cozinha_id()
        if cozinha_id:
            produtos = produtos.filter(cozinha_id=cozinha_id)
        form.fields["produto"].queryset = produtos.filter(
            Q(ativo=True) | Q(pk=form.instance.produto_id))


class ItemInline(TabularInline):
    model = ItemListaCompra
    formset = ItensInlineFormSet
    extra = 1
    fields = ["produto", "quantidade", "fornecedor", "preco_estimado", "subtotal_fmt", "comprado"]
    readonly_fields = ["subtotal_fmt"]
    autocomplete_fields = ["fornecedor"]

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.usuario = request.user
        return formset

    @display(description="subtotal")
    def subtotal_fmt(self, obj):
        return f"R$ {obj.subtotal:.2f}".replace(".", ",") if obj.pk else "—"


@admin.register(ListaCompra)
class ListaCompraAdmin(EscopoCozinhaMixin, ModelAdmin):
    list_display = ["titulo", "cozinha", "status_badge", "data_prevista", "n_itens",
                    "progresso_fmt", "total_fmt", "criada_por"]
    search_fields = ["titulo", "itens__produto__nome"]
    list_filter = [
        ("status", ChoicesCheckboxFilter),
        ("cozinha", RelatedDropdownFilter),
        ("criada_por", RelatedDropdownFilter),
        ("data_prevista", RangeDateFilter),
        ("criada_em", RangeDateFilter),
    ]
    list_filter_submit = True
    inlines = [ItemInline]
    readonly_fields = ["criada_por", "criada_em", "concluida_em", "total_fmt", "progresso_fmt"]
    actions = ["marcar_enviada", "marcar_concluida"]
    fieldsets = [
        (None, {"fields": ["cozinha", "titulo", "status", "data_prevista", "observacoes"]}),
        ("Resumo", {"fields": ["total_fmt", "progresso_fmt", "criada_por", "criada_em",
                               "concluida_em"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("cozinha", "criada_por").annotate(
            itens_total=Count("itens", distinct=True),
            itens_comprados=Count("itens", filter=Q(itens__comprado=True), distinct=True))

    def save_model(self, request, obj, form, change):
        if not change:
            obj.criada_por = request.user
        super().save_model(request, obj, form, change)

    @display(description="status", ordering="status", label=COR_STATUS)
    def status_badge(self, obj):
        return obj.get_status_display()

    @display(description="itens", ordering="itens_total")
    def n_itens(self, obj):
        return obj.itens_total

    @display(description="comprado")
    def progresso_fmt(self, obj):
        return f"{obj.progresso}%" if obj.pk else "—"

    @display(description="total estimado")
    def total_fmt(self, obj):
        return f"R$ {obj.total_estimado:.2f}".replace(".", ",") if obj.pk else "—"

    @admin.action(description="Marcar como enviadas ao fornecedor", permissions=["change"])
    def marcar_enviada(self, request, queryset):
        n = queryset.filter(status=ListaCompra.Status.RASCUNHO).update(
            status=ListaCompra.Status.ENVIADA)
        self.message_user(request, f"{n} lista(s) marcada(s) como enviada(s).", messages.SUCCESS)

    @admin.action(description="Marcar como concluídas", permissions=["change"])
    def marcar_concluida(self, request, queryset):
        n = 0
        for lista in queryset.exclude(status__in=[ListaCompra.Status.CONCLUIDA,
                                                  ListaCompra.Status.CANCELADA]):
            lista.status = ListaCompra.Status.CONCLUIDA
            lista.save()   # save() preenche concluida_em
            n += 1
        self.message_user(request, f"{n} lista(s) concluída(s).", messages.SUCCESS)
