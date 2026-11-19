"""Indicadores de estoque usados pelo painel do admin e pelo painel da área do usuário."""
from apps.core.mixins import eh_admin_geral, escopo
from apps.estoque.models import Lote, Movimentacao, Produto


def indicadores_estoque(user):
    """Consultas do painel, já filtradas pela cozinha do usuário (o Administrador vê todas)."""
    produtos = escopo(user, Produto.objects.filter(ativo=True))
    lotes = escopo(user, Lote.objects.select_related("produto", "local"), "produto__cozinha")
    return {
        "produtos": produtos,
        "lotes": lotes,
        "abaixo": produtos.abaixo_do_minimo().select_related("categoria").order_by("saldo"),
        "vencidos": lotes.vencidos(),
        "vencendo": lotes.vencendo(),
        "movimentacoes": escopo(user, Movimentacao.objects.all(), "lote__produto__cozinha"),
        "escopo": "todas as cozinhas" if eh_admin_geral(user) else str(user.cozinha or "sem cozinha"),
    }


def lotes_em_risco(indicadores, limite=8):
    """Primeiro o que ainda dá para aproveitar (vence logo), depois os vencidos mais recentes."""
    em_risco = list(indicadores["vencendo"].order_by("data_validade")[:limite])
    em_risco += list(indicadores["vencidos"].order_by("-data_validade")[:limite - len(em_risco)])
    return em_risco
