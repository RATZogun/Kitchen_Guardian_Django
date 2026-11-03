"""Callbacks do Unfold: painel inicial do admin, badges da barra lateral e ambiente."""
import json
from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.urls import reverse

from apps.core.admin_mixins import eh_admin_geral
from apps.estoque.models import Lote, Movimentacao, Produto, hoje


def _escopo(request, qs, caminho):
    if eh_admin_geral(request):
        return qs
    return qs.filter(**{caminho: request.user.cozinha_id})


def ambiente(request):
    return ["Desenvolvimento", "warning"] if settings.DEBUG else None


def badge_abaixo_minimo(request):
    n = _escopo(request, Produto.objects.abaixo_do_minimo(), "cozinha").count()
    return n or None


def badge_lotes_em_risco(request):
    n = _escopo(request, Lote.objects.em_risco(), "produto__cozinha").count()
    return n or None


def _br(valor):
    return f"{valor.normalize():f}".replace(".", ",")


def dashboard_callback(request, context):
    produtos = _escopo(request, Produto.objects.filter(ativo=True), "cozinha")
    lotes = _escopo(request, Lote.objects.select_related("produto", "local"), "produto__cozinha")
    movs = _escopo(request, Movimentacao.objects.all(), "lote__produto__cozinha")

    abaixo = produtos.abaixo_do_minimo().select_related("categoria").order_by("saldo")
    vencidos = lotes.vencidos()
    vencendo = lotes.vencendo()
    valor_total = sum((l.valor_em_estoque for l in lotes.com_saldo()), start=0)
    url_lotes = reverse("admin:estoque_lote_changelist")
    url_produtos = reverse("admin:estoque_produto_changelist")

    kpis = [
        {"titulo": "Produtos ativos", "valor": produtos.count(), "icone": "inventory_2",
         "link": url_produtos},
        {"titulo": "Abaixo do mínimo", "valor": abaixo.count(), "icone": "trending_down",
         "link": url_produtos + "?nivel=BAIXO"},
        {"titulo": "Lotes vencendo em 7 dias", "valor": vencendo.count(), "icone": "schedule",
         "link": url_lotes + "?situacao=VENCENDO"},
        {"titulo": "Lotes vencidos com saldo", "valor": vencidos.count(), "icone": "dangerous",
         "link": url_lotes + "?situacao=VENCIDO"},
        {"titulo": "Valor em estoque", "valor": f"R$ {valor_total:,.2f}".replace(",", "X")
            .replace(".", ",").replace("X", "."), "icone": "payments", "link": url_lotes},
    ]

    # primeiro o que ainda dá para aproveitar (vence logo), depois os vencidos mais recentes
    em_risco = list(vencendo.order_by("data_validade")[:8])
    em_risco += list(vencidos.order_by("-data_validade")[:8 - len(em_risco)])
    tabela_risco = {
        "headers": ["Produto", "Lote", "Local", "Restante", "Validade", "Situação"],
        "rows": [[l.produto.nome, l.codigo or f"#{l.pk}", l.local.nome,
                  f"{_br(l.quantidade_atual)} {l.produto.unidade}",
                  l.data_validade.strftime("%d/%m/%Y"),
                  "vencido" if l.situacao == "VENCIDO" else f"{l.dias_para_vencer} dia(s)"]
                 for l in em_risco],
    }
    tabela_minimo = {
        "headers": ["Produto", "Categoria", "Saldo", "Mínimo"],
        "rows": [[p.nome, p.categoria.nome, f"{_br(p.saldo)} {p.unidade}",
                  f"{_br(p.estoque_minimo)} {p.unidade}"] for p in abaixo[:8]],
    }

    # Gráfico: quantidade de movimentações por dia nos últimos 14 dias
    dias = [hoje() - timedelta(days=i) for i in range(13, -1, -1)]
    serie = {tipo: {d: 0 for d in dias} for tipo in Movimentacao.Tipo.values}
    for m in movs.filter(data__gte=dias[0]).values("data", "tipo"):
        serie[m["tipo"]][m["data"]] += 1
    grafico = json.dumps({
        "labels": [d.strftime("%d/%m") for d in dias],
        "datasets": [
            {"label": "Entradas", "data": list(serie["ENTRADA"].values()),
             "backgroundColor": "#5b8c2a"},
            {"label": "Saídas", "data": list(serie["SAIDA"].values()),
             "backgroundColor": "#94a3b8"},
            {"label": "Descartes", "data": list(serie["DESCARTE"].values()),
             "backgroundColor": "#dc2626"},
        ],
    })

    descartado = movs.filter(tipo=Movimentacao.Tipo.DESCARTE, data__gte=dias[0]) \
        .aggregate(t=Sum("quantidade"))["t"]

    context.update({
        "kpis": kpis,
        "tabela_risco": tabela_risco,
        "tabela_minimo": tabela_minimo,
        "grafico_movimentacoes": grafico,
        "n_movs_14d": movs.filter(data__gte=dias[0]).count(),
        "descartes_14d": movs.filter(tipo=Movimentacao.Tipo.DESCARTE, data__gte=dias[0]).count(),
        "tem_descarte": bool(descartado),
        "escopo": "todas as cozinhas" if eh_admin_geral(request)
                  else str(request.user.cozinha or "sem cozinha"),
    })
    return context
