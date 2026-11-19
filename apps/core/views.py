from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.compras.models import ListaCompra
from apps.core.indicadores import indicadores_estoque, lotes_em_risco
from apps.core.mixins import escopo
from apps.cozinhas.models import Cozinha
from apps.estoque.models import Lote, Produto


def inicio(request):
    """Página pública de apresentação."""
    contexto = {
        "n_cozinhas": Cozinha.objects.filter(ativa=True).count(),
        "n_produtos": Produto.objects.filter(ativo=True).count(),
        "n_lotes": Lote.objects.com_saldo().count(),
    }
    return render(request, "core/inicio.html", contexto)


@login_required
def painel(request):
    """Página inicial da área do usuário: alertas da cozinha e atalhos."""
    ind = indicadores_estoque(request.user)
    contexto = {
        "escopo": ind["escopo"],
        "n_produtos": ind["produtos"].count(),
        "n_abaixo": ind["abaixo"].count(),
        "n_vencendo": ind["vencendo"].count(),
        "n_vencidos": ind["vencidos"].count(),
        "abaixo": ind["abaixo"][:6],
        "em_risco": lotes_em_risco(ind, limite=8),
        "movimentacoes": ind["movimentacoes"].select_related("lote__produto", "usuario")[:8],
        "listas_abertas": escopo(request.user, ListaCompra.objects.com_resumo().exclude(
            status__in=[ListaCompra.Status.CONCLUIDA, ListaCompra.Status.CANCELADA]))[:5],
    }
    return render(request, "core/painel.html", contexto)
