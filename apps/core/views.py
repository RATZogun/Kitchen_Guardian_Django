from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.compras.models import ListaCompra
from apps.core.mixins import eh_admin_geral, escopo
from apps.cozinhas.models import Cozinha
from apps.estoque.models import Lote, Movimentacao, Produto


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
    user = request.user
    produtos = escopo(user, Produto.objects.filter(ativo=True))
    lotes = escopo(user, Lote.objects.select_related("produto", "local"), "produto__cozinha")
    abaixo = produtos.abaixo_do_minimo().select_related("categoria").order_by("saldo")
    vencidos = lotes.vencidos()
    vencendo = lotes.vencendo()
    contexto = {
        "escopo": "todas as cozinhas" if eh_admin_geral(user) else user.cozinha,
        "n_produtos": produtos.count(),
        "n_abaixo": abaixo.count(),
        "n_vencendo": vencendo.count(),
        "n_vencidos": vencidos.count(),
        "abaixo": abaixo[:6],
        "em_risco": list(vencidos.order_by("data_validade")[:6])
                    + list(vencendo.order_by("data_validade")[:6]),
        "movimentacoes": escopo(user, Movimentacao.objects.select_related("lote__produto", "usuario"),
                                "lote__produto__cozinha")[:8],
        "listas_abertas": escopo(user, ListaCompra.objects.exclude(
            status__in=[ListaCompra.Status.CONCLUIDA, ListaCompra.Status.CANCELADA]))[:5],
    }
    return render(request, "core/painel.html", contexto)
