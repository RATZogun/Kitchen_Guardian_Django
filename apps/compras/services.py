from decimal import Decimal

from django.db import transaction

from apps.estoque.models import Lote, Produto, hoje

from .models import ItemListaCompra, ListaCompra

#: a reposição sugerida leva o saldo até este múltiplo do estoque mínimo
FATOR_REPOSICAO = Decimal("2")


@transaction.atomic
def gerar_lista_reposicao(cozinha, usuario):
    """Cria uma lista em rascunho com os produtos da cozinha abaixo do estoque mínimo.

    A quantidade sugerida leva o saldo a 2x o mínimo; o preço estimado é o custo
    do lote mais recente do produto. Retorna None se nada estiver faltando.
    """
    faltando = Produto.objects.abaixo_do_minimo().filter(cozinha=cozinha) \
        .select_related("fornecedor_padrao")
    if not faltando.exists():
        return None
    lista = ListaCompra.objects.create(
        cozinha=cozinha, criada_por=usuario,
        titulo=f"Reposição de {hoje():%d/%m/%Y}",
        observacoes="Gerada a partir dos produtos abaixo do estoque mínimo.")
    for produto in faltando:
        alvo = max(produto.estoque_minimo * FATOR_REPOSICAO, Decimal("1"))
        ultimo = Lote.objects.filter(produto=produto, custo_unitario__isnull=False) \
            .order_by("-data_entrada", "-pk").first()
        ItemListaCompra.objects.create(
            lista=lista, produto=produto, quantidade=max(alvo - produto.saldo, Decimal("1")),
            fornecedor=produto.fornecedor_padrao,
            preco_estimado=ultimo.custo_unitario if ultimo else Decimal("0"))
    return lista
