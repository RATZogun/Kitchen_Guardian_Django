"""Regras de negócio do estoque.

Toda alteração de saldo passa por aqui, dentro de uma transação, e gera uma
Movimentacao com o usuário responsável (RF012: rastreabilidade).
O saldo nunca é editado diretamente (RF008/RN01).
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Lote, Movimentacao, hoje


@transaction.atomic
def registrar_entrada(lote, usuario, motivo=Movimentacao.Motivo.COMPRA, observacao=""):
    """RF010: cria o lote com o saldo cheio e registra a movimentação de entrada."""
    if lote.pk:
        raise ValidationError("Este lote já foi registrado.")
    lote.quantidade_atual = lote.quantidade_inicial
    lote.registrado_por = usuario
    lote.full_clean()
    lote.save()
    return Movimentacao.objects.create(
        lote=lote, tipo=Movimentacao.Tipo.ENTRADA, motivo=motivo,
        quantidade=lote.quantidade_inicial, data=lote.data_entrada,
        usuario=usuario, observacao=observacao)


@transaction.atomic
def registrar_baixa(lote, quantidade, usuario, tipo=Movimentacao.Tipo.SAIDA,
                    motivo=Movimentacao.Motivo.PREPARO, data=None, observacao=""):
    """RF011: saída por consumo ou descarte, sem deixar o lote negativo."""
    if tipo == Movimentacao.Tipo.ENTRADA:
        raise ValidationError("Use registrar_entrada para entradas.")
    lote = Lote.objects.select_for_update().get(pk=lote.pk)   # evita corrida entre operadores
    data = data or hoje()
    if quantidade is None or quantidade <= 0:
        raise ValidationError({"quantidade": "A quantidade deve ser positiva."})
    if quantidade > lote.quantidade_atual:
        raise ValidationError({"quantidade":
                               f"Saldo insuficiente no lote: restam {lote.quantidade_atual} "
                               f"{lote.produto.unidade}."})
    if data > hoje():
        raise ValidationError({"data": "A data não pode ser futura."})
    if data < lote.data_entrada:
        raise ValidationError({"data": "A data não pode ser anterior à entrada do lote."})

    lote.quantidade_atual -= quantidade
    lote.save(update_fields=["quantidade_atual"])
    return Movimentacao.objects.create(
        lote=lote, tipo=tipo, motivo=motivo, quantidade=quantidade, data=data,
        usuario=usuario, observacao=observacao)


@transaction.atomic
def descartar_vencidos(lotes, usuario):
    """Descarta todo o saldo dos lotes vencidos informados. Retorna quantos baixou."""
    total = 0
    for lote in lotes.vencidos():
        registrar_baixa(lote, lote.quantidade_atual, usuario,
                        tipo=Movimentacao.Tipo.DESCARTE, motivo=Movimentacao.Motivo.VENCIMENTO,
                        observacao="Descarte em lote de produtos vencidos")
        total += 1
    return total
