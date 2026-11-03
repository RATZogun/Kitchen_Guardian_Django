from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.contas.models import Usuario
from apps.cozinhas.models import Cozinha, LocalArmazenamento
from apps.estoque import services
from apps.estoque.models import Categoria, Lote, Movimentacao, Produto, hoje


class BaseEstoque(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cozinha = Cozinha.objects.create(nome="RU")
        cls.local = LocalArmazenamento.objects.create(cozinha=cls.cozinha, nome="Despensa")
        cls.usuario = Usuario.objects.create_user("op", password="x", perfil="OPERADOR",
                                                  cozinha=cls.cozinha)
        cls.categoria = Categoria.objects.create(nome="Grãos")
        cls.produto = Produto.objects.create(cozinha=cls.cozinha, nome="Arroz", unidade="kg",
                                             categoria=cls.categoria, estoque_minimo=10)

    def novo_lote(self, quantidade="20", validade_em=30, entrada_ha=0):
        lote = Lote(produto=self.produto, local=self.local,
                    quantidade_inicial=Decimal(quantidade),
                    data_entrada=hoje() - timedelta(days=entrada_ha),
                    data_validade=hoje() + timedelta(days=validade_em))
        services.registrar_entrada(lote, self.usuario)
        return lote


class RegrasDeEstoqueTest(BaseEstoque):
    def test_entrada_cria_lote_cheio_e_movimentacao(self):
        lote = self.novo_lote("20")
        self.assertEqual(lote.quantidade_atual, Decimal("20"))
        mov = lote.movimentacoes.get()
        self.assertEqual((mov.tipo, mov.quantidade, mov.usuario), ("ENTRADA", 20, self.usuario))

    def test_saida_baixa_o_saldo_do_produto(self):
        lote = self.novo_lote("20")
        services.registrar_baixa(lote, Decimal("7.5"), self.usuario)
        lote.refresh_from_db()
        self.assertEqual(lote.quantidade_atual, Decimal("12.5"))
        produto = Produto.objects.com_saldo().get(pk=self.produto.pk)
        self.assertEqual(produto.saldo, Decimal("12.5"))
        self.assertEqual(produto.nivel, "OK")

    def test_saida_maior_que_o_saldo_e_recusada(self):
        lote = self.novo_lote("5")
        with self.assertRaises(ValidationError):
            services.registrar_baixa(lote, Decimal("6"), self.usuario)
        lote.refresh_from_db()
        self.assertEqual(lote.quantidade_atual, Decimal("5"))
        self.assertEqual(Movimentacao.objects.filter(tipo="SAIDA").count(), 0)

    def test_saida_com_data_futura_e_recusada(self):
        lote = self.novo_lote("5")
        with self.assertRaises(ValidationError):
            services.registrar_baixa(lote, Decimal("1"), self.usuario,
                                     data=hoje() + timedelta(days=1))

    def test_entrada_com_data_futura_e_recusada(self):
        lote = Lote(produto=self.produto, local=self.local, quantidade_inicial=1,
                    data_entrada=hoje() + timedelta(days=1),
                    data_validade=hoje() + timedelta(days=9))
        with self.assertRaises(ValidationError):
            services.registrar_entrada(lote, self.usuario)

    def test_perecivel_exige_validade(self):
        lote = Lote(produto=self.produto, local=self.local, quantidade_inicial=1)
        with self.assertRaises(ValidationError):
            services.registrar_entrada(lote, self.usuario)

    def test_local_de_outra_cozinha_e_recusado(self):
        outra = Cozinha.objects.create(nome="Cantina")
        local = LocalArmazenamento.objects.create(cozinha=outra, nome="Geladeira")
        lote = Lote(produto=self.produto, local=local, quantidade_inicial=1,
                    data_validade=hoje() + timedelta(days=5))
        with self.assertRaises(ValidationError):
            services.registrar_entrada(lote, self.usuario)

    def test_abaixo_do_minimo_e_alertas_de_validade(self):
        self.novo_lote("4", validade_em=3)                  # vence em 3 dias
        self.novo_lote("3", validade_em=-2, entrada_ha=10)  # já vencido
        self.assertIn(self.produto, Produto.objects.abaixo_do_minimo())   # 7 <= 10
        self.assertEqual(Lote.objects.vencendo().count(), 1)
        self.assertEqual(Lote.objects.vencidos().count(), 1)
        self.assertEqual(Lote.objects.em_risco().count(), 2)

    def test_descartar_vencidos_zera_so_os_vencidos(self):
        bom = self.novo_lote("4", validade_em=10)
        vencido = self.novo_lote("3", validade_em=-1, entrada_ha=5)
        n = services.descartar_vencidos(Lote.objects.all(), self.usuario)
        self.assertEqual(n, 1)
        bom.refresh_from_db()
        vencido.refresh_from_db()
        self.assertEqual((bom.quantidade_atual, vencido.quantidade_atual), (4, 0))
        self.assertEqual(vencido.movimentacoes.filter(tipo="DESCARTE").count(), 1)

    def test_categoria_com_produto_ativo_nao_pode_ser_desativada(self):
        self.categoria.ativo = False
        with self.assertRaises(ValidationError):
            self.categoria.full_clean()
