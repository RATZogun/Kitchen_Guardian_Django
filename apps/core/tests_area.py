"""Testes da área do usuário: autenticação, cadastro, telas, CRUD e permissões por perfil."""
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.compras.models import ListaCompra
from apps.contas.models import Usuario
from apps.cozinhas.models import Cozinha, LocalArmazenamento
from apps.estoque.models import Categoria, Lote, Movimentacao, Produto


class AreaUsuarioTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("popular_demo", stdout=open("/dev/null", "w"))
        cls.admin = Usuario.objects.get(username="admin")
        cls.gestor = Usuario.objects.get(username="gestor1")
        cls.operador = Usuario.objects.get(username="operador1")
        cls.outro_gestor = Usuario.objects.get(username="gestor2")

    # ------------------------------------------------------------------
    # Autenticação
    # ------------------------------------------------------------------
    def test_login_e_logout(self):
        r = self.client.post(reverse("contas:login"),
                             {"username": "operador1", "password": "guardiao123"})
        self.assertRedirects(r, reverse("core:painel"))
        r = self.client.post(reverse("contas:logout"))
        self.assertRedirects(r, reverse("core:inicio"))
        r = self.client.get(reverse("core:painel"))
        self.assertRedirects(r, reverse("contas:login") + "?next=" + reverse("core:painel"))

    def test_login_com_senha_errada(self):
        r = self.client.post(reverse("contas:login"), {"username": "operador1", "password": "x"})
        self.assertContains(r, "Usuário ou senha incorretos")

    def test_cadastro_cria_usuario_gestor_e_cozinha(self):
        r = self.client.post(reverse("contas:cadastro"), {
            "first_name": "Rita", "last_name": "Souza", "username": "rita",
            "email": "rita@exemplo.com", "password1": "Cozinha#2026", "password2": "Cozinha#2026",
            "nome_cozinha": "Casa da Rita", "tipo_cozinha": "DOMESTICA", "cidade": "Lavras"})
        self.assertRedirects(r, reverse("core:painel"))
        rita = Usuario.objects.get(username="rita")
        self.assertEqual(rita.perfil, Usuario.Perfil.GESTOR)
        self.assertEqual(rita.cozinha.nome, "Casa da Rita")
        self.assertEqual(rita.cozinha.responsavel, rita)
        self.assertEqual(rita.cozinha.locais.count(), 3)
        self.assertTrue(rita.groups.filter(name="Gestor").exists())

    def test_cadastro_rejeita_email_e_cozinha_repetidos(self):
        r = self.client.post(reverse("contas:cadastro"), {
            "first_name": "X", "username": "novo", "email": self.gestor.email,
            "password1": "Cozinha#2026", "password2": "Cozinha#2026",
            "nome_cozinha": Cozinha.objects.first().nome, "tipo_cozinha": "DOMESTICA"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("email", r.context["form"].errors)
        self.assertIn("nome_cozinha", r.context["form"].errors)

    # ------------------------------------------------------------------
    # Telas
    # ------------------------------------------------------------------
    def test_todas_as_telas_abrem_para_cada_perfil(self):
        produto = Produto.objects.filter(cozinha=self.gestor.cozinha).first()
        lote = Lote.objects.com_saldo().filter(produto__cozinha=self.gestor.cozinha).first()
        lista = ListaCompra.objects.filter(cozinha=self.gestor.cozinha).first() or \
            ListaCompra.objects.create(cozinha=self.gestor.cozinha, titulo="Teste")
        urls = [reverse("core:painel"), reverse("estoque:produtos"),
                reverse("estoque:produto", args=[produto.pk]), reverse("estoque:lotes"),
                reverse("estoque:lotes") + "?situacao=VENCIDO", reverse("estoque:movimentacoes"),
                reverse("estoque:baixa", args=[lote.pk]), reverse("estoque:entrada"),
                reverse("compras:listas"), reverse("compras:lista", args=[lista.pk]),
                reverse("cozinhas:locais"), reverse("contas:perfil"), reverse("contas:senha")]
        for usuario in (self.admin, self.gestor, self.operador):
            self.client.force_login(usuario)
            for url in urls:
                with self.subTest(usuario=usuario.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_paginas_publicas(self):
        for nome in ("core:inicio", "contas:login", "contas:cadastro"):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 200)

    # ------------------------------------------------------------------
    # CRUD e regras
    # ------------------------------------------------------------------
    def test_gestor_faz_crud_de_produto(self):
        self.client.force_login(self.gestor)
        categoria = Categoria.objects.first()
        dados = {"nome": "Quinoa", "categoria": categoria.pk, "unidade": "kg",
                 "estoque_minimo": "2", "perecivel": "on", "ativo": "on"}
        r = self.client.post(reverse("estoque:produto_novo"), dados)
        produto = Produto.objects.get(nome="Quinoa")
        self.assertRedirects(r, reverse("estoque:produto", args=[produto.pk]))
        self.assertEqual(produto.cozinha, self.gestor.cozinha)   # vem do usuário
        self.assertEqual(produto.criado_por, self.gestor)

        # nome repetido na mesma cozinha é recusado
        r = self.client.post(reverse("estoque:produto_novo"), dados)
        self.assertIn("nome", r.context["form"].errors)

        dados["estoque_minimo"] = "5"
        self.client.post(reverse("estoque:produto_editar", args=[produto.pk]), dados)
        produto.refresh_from_db()
        self.assertEqual(produto.estoque_minimo, Decimal("5"))

        self.client.post(reverse("estoque:produto_excluir", args=[produto.pk]))
        self.assertFalse(Produto.objects.filter(pk=produto.pk).exists())

    def test_excluir_produto_com_lotes_mostra_aviso(self):
        self.client.force_login(self.gestor)
        produto = Lote.objects.filter(produto__cozinha=self.gestor.cozinha).first().produto
        r = self.client.post(reverse("estoque:produto_excluir", args=[produto.pk]), follow=True)
        self.assertContains(r, "Não é possível excluir")
        self.assertTrue(Produto.objects.filter(pk=produto.pk).exists())

    def test_operador_registra_entrada_e_baixa(self):
        self.client.force_login(self.operador)
        produto = Produto.objects.filter(cozinha=self.operador.cozinha, perecivel=True).first()
        local = LocalArmazenamento.objects.filter(cozinha=self.operador.cozinha).first()
        r = self.client.post(reverse("estoque:entrada"), {
            "produto": produto.pk, "local": local.pk, "codigo": "TESTE-1",
            "quantidade_inicial": "10", "data_entrada": "2026-01-10",
            "data_validade": "2099-01-01", "motivo": "COMPRA"})
        lote = Lote.objects.get(codigo="TESTE-1")
        self.assertRedirects(r, reverse("estoque:produto", args=[produto.pk]))
        self.assertEqual(lote.quantidade_atual, Decimal("10"))
        self.assertEqual(lote.registrado_por, self.operador)

        r = self.client.post(reverse("estoque:baixa", args=[lote.pk]), {
            "tipo": "SAIDA", "motivo": "PREPARO", "quantidade": "4", "data": "2026-01-11"})
        lote.refresh_from_db()
        self.assertEqual(lote.quantidade_atual, Decimal("6"))
        self.assertTrue(Movimentacao.objects.filter(lote=lote, tipo="SAIDA",
                                                    usuario=self.operador).exists())

        # não deixa o lote ficar negativo
        r = self.client.post(reverse("estoque:baixa", args=[lote.pk]), {
            "tipo": "SAIDA", "motivo": "PREPARO", "quantidade": "100", "data": "2026-01-11"})
        self.assertContains(r, "Saldo insuficiente")

    def test_perecivel_sem_validade_e_recusado(self):
        self.client.force_login(self.operador)
        produto = Produto.objects.filter(cozinha=self.operador.cozinha, perecivel=True).first()
        local = LocalArmazenamento.objects.filter(cozinha=self.operador.cozinha).first()
        r = self.client.post(reverse("estoque:entrada"), {
            "produto": produto.pk, "local": local.pk, "quantidade_inicial": "1",
            "data_entrada": "2026-01-10", "motivo": "COMPRA"})
        self.assertIn("data_validade", r.context["form"].errors)

    def test_gestor_gera_lista_e_marca_item(self):
        self.client.force_login(self.gestor)
        r = self.client.post(reverse("compras:gerar"))
        lista = ListaCompra.objects.filter(cozinha=self.gestor.cozinha).order_by("-pk").first()
        self.assertRedirects(r, reverse("compras:lista", args=[lista.pk]))
        self.assertTrue(lista.itens.exists())
        item = lista.itens.first()
        self.client.post(reverse("compras:item_comprado", args=[item.pk]))
        item.refresh_from_db()
        self.assertTrue(item.comprado)

    # ------------------------------------------------------------------
    # Permissões
    # ------------------------------------------------------------------
    def test_operador_nao_cadastra_produto_nem_lista(self):
        self.client.force_login(self.operador)
        for url in (reverse("estoque:produto_novo"), reverse("compras:lista_nova"),
                    reverse("cozinhas:local_novo")):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), reverse("core:painel"))
        self.assertEqual(self.client.post(reverse("compras:gerar")).status_code, 403)

    def test_usuario_nao_ve_dados_de_outra_cozinha(self):
        produto_alheio = Produto.objects.filter(cozinha=self.outro_gestor.cozinha).first()
        self.client.force_login(self.gestor)
        self.assertEqual(self.client.get(
            reverse("estoque:produto", args=[produto_alheio.pk])).status_code, 404)
        r = self.client.get(reverse("estoque:produtos") + "?inativos=1")
        self.assertNotIn(produto_alheio, r.context["object_list"])

    def test_admin_ve_todas_as_cozinhas(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("estoque:produtos") + "?inativos=1")
        self.assertEqual(r.context["paginator"].count, Produto.objects.count())
