from django import forms

from apps.core.forms import BootstrapMixin, NomeUnicoNaCozinhaMixin

from .models import Produto


class ProdutoForm(BootstrapMixin, NomeUnicoNaCozinhaMixin, forms.ModelForm):
    class Meta:
        model = Produto
        fields = ["cozinha", "nome", "categoria", "fornecedor_padrao", "unidade",
                  "estoque_minimo", "perecivel", "codigo_barras", "ativo"]
