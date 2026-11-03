"""Testes do ambiente administrativo: todas as telas abrem, filtros funcionam e cada
perfil enxerga apenas o que deve."""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.contas.models import Usuario
from apps.estoque.models import Lote, Produto

LISTAGENS = [
    "contas_usuario", "auth_group", "cozinhas_cozinha", "cozinhas_localarmazenamento",
    "estoque_categoria", "estoque_fornecedor", "estoque_produto", "estoque_lote",
    "estoque_movimentacao", "compras_listacompra",
]

FILTROS = {
    "estoque_produto": ["nivel=BAIXO", "nivel=ZERADO", "risco=SIM", "risco=NAO",
                        "unidade__exact=kg", "perecivel__exact=1",
                        "estoque_minimo_from=1&estoque_minimo_to=50",
                        "criado_em_from_0=01/01/2020&criado_em_to_0=31/12/2099"],
    "estoque_lote": ["situacao=VENCIDO", "situacao=VENCENDO", "situacao=OK", "situacao=SEM",
                     "situacao=ESGOTADO", "local__tipo__exact=FREEZER",
                     "data_validade_from=01/01/2020&data_validade_to=31/12/2099"],
    "estoque_movimentacao": ["tipo__exact=DESCARTE", "motivo__exact=PREPARO",
                             "quantidade_from=1&quantidade_to=10"],
    "compras_listacompra": ["status__exact=RASCUNHO"],
    "contas_usuario": ["perfil__exact=GESTOR", "is_active__exact=1"],
}


class AdminTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("popular_demo", stdout=open("/dev/null", "w"))
        cls.admin = Usuario.objects.get(username="admin")
        cls.gestor = Usuario.objects.get(username="gestor1")
        cls.operador = Usuario.objects.get(username="operador1")

    def test_todas_as_listagens_e_formularios_abrem(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
        for nome in LISTAGENS:
            with self.subTest(nome):
                self.assertEqual(self.client.get(reverse(f"admin:{nome}_changelist")).status_code, 200)
                self.assertEqual(self.client.get(reverse(f"admin:{nome}_add")).status_code, 200)

    def test_paginas_de_edicao_abrem(self):
        self.client.force_login(self.admin)
        for url in [reverse("admin:estoque_produto_change", args=[Produto.objects.first().pk]),
                    reverse("admin:estoque_lote_change", args=[Lote.objects.first().pk])]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_filtros(self):
        self.client.force_login(self.admin)
        for nome, filtros in FILTROS.items():
            for f in filtros:
                with self.subTest(f"{nome}?{f}"):
                    resp = self.client.get(reverse(f"admin:{nome}_changelist") + "?" + f)
                    self.assertEqual(resp.status_code, 200)   # filtro inválido daria 302

    def test_filtro_nivel_baixo_bate_com_a_regra(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin:estoque_produto_changelist") + "?nivel=BAIXO")
        esperado = Produto.objects.abaixo_do_minimo().count()
        self.assertEqual(resp.context["cl"].result_count, esperado)

    def test_gestor_ve_so_a_propria_cozinha(self):
        self.client.force_login(self.gestor)
        resp = self.client.get(reverse("admin:estoque_produto_changelist"))
        self.assertEqual(resp.status_code, 200)
        cozinhas = {p.cozinha_id for p in resp.context["cl"].queryset}
        self.assertEqual(cozinhas, {self.gestor.cozinha_id})
        outro = Produto.objects.exclude(cozinha=self.gestor.cozinha).first()
        url = reverse("admin:estoque_produto_change", args=[outro.pk])
        self.assertNotEqual(self.client.get(url).status_code, 200)

    def test_gestor_nao_edita_usuarios(self):
        self.client.force_login(self.gestor)
        self.assertEqual(self.client.get(reverse("admin:contas_usuario_add")).status_code, 403)

    def test_operador_nao_entra_no_admin(self):
        self.client.force_login(self.operador)
        resp = self.client.get(reverse("admin:index"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("admin:login"), resp.url)

    def test_movimentacoes_sao_imutaveis(self):
        self.client.force_login(self.admin)
        mov = self.admin.movimentacoes.first() or Lote.objects.first().movimentacoes.first()
        url = reverse("admin:estoque_movimentacao_delete", args=[mov.pk])
        self.assertEqual(self.client.post(url, {"post": "yes"}).status_code, 403)

    def test_registrar_saida_pelo_admin(self):
        self.client.force_login(self.admin)
        lote = Lote.objects.filter(quantidade_atual__gte=2).first()
        antes = lote.quantidade_atual
        resp = self.client.post(reverse("admin:estoque_movimentacao_add"), {
            "lote": lote.pk, "tipo": "SAIDA", "motivo": "PREPARO", "quantidade": "1",
            "data": "", "observacao": "teste"})
        # data vazia é inválida: o formulário deve voltar com erro, sem mexer no saldo
        self.assertEqual(resp.status_code, 200)
        lote.refresh_from_db()
        self.assertEqual(lote.quantidade_atual, antes)

    def test_pagina_inicial(self):
        resp = self.client.get(reverse("core:inicio"))
        self.assertContains(resp, "Guardião da Cozinha")
        self.assertContains(resp, "data-bs-theme")


class PerfisTest(TestCase):
    def test_grupos_criados_e_usuario_sincronizado(self):
        from django.contrib.auth.models import Group
        self.assertEqual(set(Group.objects.values_list("name", flat=True)),
                         {"Administrador", "Gestor", "Operador"})
        u = Usuario.objects.create_user("x", password="x", perfil="GESTOR")
        self.assertTrue(u.is_staff)
        self.assertEqual(list(u.groups.values_list("name", flat=True)), ["Gestor"])
        u.perfil = "OPERADOR"
        u.save()
        self.assertFalse(u.is_staff)
        self.assertEqual(list(u.groups.values_list("name", flat=True)), ["Operador"])
        self.assertTrue(u.has_perm("estoque.add_movimentacao"))
        self.assertFalse(u.has_perm("estoque.delete_produto"))
