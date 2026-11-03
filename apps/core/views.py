from django.shortcuts import render

from apps.cozinhas.models import Cozinha
from apps.estoque.models import Lote, Produto


def inicio(request):
    """Página pública de apresentação. A área do usuário entra no Checkpoint 2."""
    contexto = {
        "n_cozinhas": Cozinha.objects.filter(ativa=True).count(),
        "n_produtos": Produto.objects.filter(ativo=True).count(),
        "n_lotes": Lote.objects.com_saldo().count(),
    }
    return render(request, "core/inicio.html", contexto)
