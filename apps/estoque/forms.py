from decimal import Decimal

from django import forms

from apps.core.forms import BootstrapMixin, NomeUnicoNaCozinhaMixin

from .models import Lote, Movimentacao, Produto


class ProdutoForm(BootstrapMixin, NomeUnicoNaCozinhaMixin, forms.ModelForm):
    class Meta:
        model = Produto
        fields = ["cozinha", "nome", "categoria", "fornecedor_padrao", "unidade",
                  "estoque_minimo", "perecivel", "codigo_barras", "ativo"]


class LoteEntradaForm(BootstrapMixin, forms.ModelForm):
    """Entrada de mercadoria: cria o lote e a movimentação de entrada."""

    motivo = forms.ChoiceField(label="motivo", initial=Movimentacao.Motivo.COMPRA, choices=[
        (Movimentacao.Motivo.COMPRA, Movimentacao.Motivo.COMPRA.label),
        (Movimentacao.Motivo.DOACAO, Movimentacao.Motivo.DOACAO.label),
        (Movimentacao.Motivo.OUTRO, Movimentacao.Motivo.OUTRO.label)])
    observacao = forms.CharField(label="observação", max_length=200, required=False)

    class Meta:
        model = Lote
        fields = ["produto", "local", "fornecedor", "codigo", "quantidade_inicial",
                  "data_entrada", "data_validade", "custo_unitario"]
        widgets = {"data_entrada": forms.DateInput(), "data_validade": forms.DateInput()}


class LoteEdicaoForm(BootstrapMixin, forms.ModelForm):
    """Só dados cadastrais: a quantidade muda apenas por movimentações."""

    class Meta:
        model = Lote
        fields = ["local", "fornecedor", "codigo", "data_validade", "custo_unitario"]
        widgets = {"data_validade": forms.DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # o local precisa continuar na cozinha do produto
        self.fields["local"].queryset = self.fields["local"].queryset.filter(
            cozinha=self.instance.produto.cozinha_id)


class BaixaForm(BootstrapMixin, forms.Form):
    tipo = forms.ChoiceField(label="tipo", choices=[
        (Movimentacao.Tipo.SAIDA, Movimentacao.Tipo.SAIDA.label),
        (Movimentacao.Tipo.DESCARTE, Movimentacao.Tipo.DESCARTE.label)])
    motivo = forms.ChoiceField(label="motivo", initial=Movimentacao.Motivo.PREPARO, choices=[
        (m, m.label) for m in (Movimentacao.Motivo.PREPARO, Movimentacao.Motivo.VENCIMENTO,
                               Movimentacao.Motivo.AVARIA, Movimentacao.Motivo.OUTRO)])
    quantidade = forms.DecimalField(label="quantidade", max_digits=10, decimal_places=3,
                                    min_value=Decimal("0.001"))
    data = forms.DateField(label="data", widget=forms.DateInput())
    observacao = forms.CharField(label="observação", max_length=200, required=False)
