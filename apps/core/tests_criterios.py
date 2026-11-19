"""Testes dos critérios de avaliação do Trabalho Prático (GAC116, Projeto de Implementação com Django).

Cada classe corresponde a uma seção do enunciado: requisitos funcionais (2), requisitos
técnicos (3), Checkpoint 1 (5.1) e Checkpoint 2 (5.2). Os nomes dos testes repetem o critério,
para a saída do `python manage.py test -v 2` servir como checklist da entrega.
"""
import re
import shutil
import subprocess
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.core.management import call_command
from django.db import models
from django.test import TestCase
from django.urls import reverse

from apps.compras.models import ListaCompra
from apps.contas.models import Usuario
from apps.cozinhas.models import LocalArmazenamento
from apps.estoque.models import Categoria, Produto

SENHA = "guardiao123"
APPS_DO_PROJETO = ["contas", "cozinhas", "estoque", "compras"]


def modelos_do_projeto():
    return [m for m in apps.get_models() if m._meta.app_label in APPS_DO_PROJETO]


class ComDadosDemo(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("popular_demo", stdout=open("/dev/null", "w"))
        cls.admin = Usuario.objects.get(username="admin")
        cls.gestor = Usuario.objects.get(username="gestor1")
        cls.operador = Usuario.objects.get(username="operador1")


# ---------------------------------------------------------------------------
# 2. Requisitos funcionais
# ---------------------------------------------------------------------------
class RequisitosFuncionaisTest(ComDadosDemo):
    def test_autenticacao_de_usuarios(self):
        r = self.client.post(reverse("contas:login"), {"username": "gestor1", "password": SENHA})
        self.assertRedirects(r, reverse("core:painel"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.gestor.pk)

    def test_crud_das_principais_entidades(self):
        """Cadastro, consulta, edição e exclusão de produtos, locais e listas de compras."""
        self.client.force_login(self.gestor)
        categoria = Categoria.objects.first()
        casos = [
            (Produto, "estoque:produto_novo", "estoque:produto_editar", "estoque:produto_excluir",
             {"nome": "Item CRUD", "categoria": categoria.pk, "unidade": "kg",
              "estoque_minimo": "1", "ativo": "on"}, "estoque_minimo", "3.000"),
            (LocalArmazenamento, "cozinhas:local_novo", "cozinhas:local_editar",
             "cozinhas:local_excluir", {"nome": "Item CRUD", "tipo": "DESPENSA", "ativo": "on"},
             "tipo", "FREEZER"),
            (ListaCompra, "compras:lista_nova", "compras:lista_editar", "compras:lista_excluir",
             {"titulo": "Item CRUD", "status": "RASCUNHO"}, "status", "ENVIADA"),
        ]
        for modelo, criar, editar, excluir, dados, campo, novo_valor in casos:
            with self.subTest(modelo=modelo.__name__):
                filtro = {"titulo": "Item CRUD"} if modelo is ListaCompra else {"nome": "Item CRUD"}
                self.client.post(reverse(criar), dados)                             # cadastro
                obj = modelo.objects.get(**filtro)
                self.assertEqual(obj.cozinha, self.gestor.cozinha)
                self.client.post(reverse(editar, args=[obj.pk]), {**dados, campo: novo_valor})
                obj.refresh_from_db()                                               # edição
                self.assertEqual(str(getattr(obj, campo)), novo_valor)
                self.client.post(reverse(excluir, args=[obj.pk]))                   # exclusão
                self.assertFalse(modelo.objects.filter(pk=obj.pk).exists())
        # consulta
        for nome in ("estoque:produtos", "estoque:lotes", "estoque:movimentacoes",
                     "compras:listas", "cozinhas:locais"):
            with self.subTest(consulta=nome):
                self.assertEqual(self.client.get(reverse(nome)).status_code, 200)

    def test_perfis_diferentes_com_permissoes_distintas(self):
        perms = {u.perfil: u.get_all_permissions() for u in (self.admin, self.gestor, self.operador)}
        self.assertGreater(len(perms["ADMIN"]), len(perms["GESTOR"]))
        self.assertGreater(len(perms["GESTOR"]), len(perms["OPERADOR"]))
        self.assertIn("estoque.add_produto", perms["GESTOR"])
        self.assertNotIn("estoque.add_produto", perms["OPERADOR"])
        self.assertIn("estoque.add_lote", perms["OPERADOR"])
        # na prática: o operador não acessa telas de cadastro nem o admin
        self.client.force_login(self.operador)
        self.assertRedirects(self.client.get(reverse("estoque:produto_novo")),
                             reverse("core:painel"))
        self.assertNotEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def test_area_administrativa_protegida_por_autenticacao(self):
        r = self.client.get(reverse("admin:index"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("admin:login"), r["Location"])
        self.client.force_login(self.gestor)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def test_area_do_usuario_protegida_por_autenticacao(self):
        for nome in ("core:painel", "estoque:produtos", "estoque:lotes", "compras:listas",
                     "cozinhas:locais", "contas:perfil"):
            with self.subTest(url=nome):
                r = self.client.get(reverse(nome))
                self.assertEqual(r.status_code, 302)
                self.assertTrue(r["Location"].startswith(reverse("contas:login")))

    def test_menus_e_navegacao_adequados_ao_perfil(self):
        self.client.force_login(self.gestor)
        html = self.client.get(reverse("core:painel")).content.decode()
        for item in ("Painel", "Estoque", "Produtos", "Lotes", "Movimentações", "Compras",
                     "Locais", "Administração", "Sair"):
            with self.subTest(menu=item):
                self.assertIn(item, html)
        self.client.force_login(self.operador)
        html = self.client.get(reverse("core:painel")).content.decode()
        self.assertNotIn(reverse("admin:index"), html)   # operador não vê o link do admin


# ---------------------------------------------------------------------------
# 3. Requisitos técnicos
# ---------------------------------------------------------------------------
class RequisitosTecnicosTest(ComDadosDemo):
    def test_framework_django_com_pelo_menos_dois_apps(self):
        nossos = [a for a in settings.INSTALLED_APPS if a.startswith("apps.")]
        self.assertGreaterEqual(len(nossos), 2)

    def test_banco_relacional_com_tabelas_e_relacionamentos(self):
        motor = settings.DATABASES["default"]["ENGINE"]
        self.assertIn(motor, ["django.db.backends.sqlite3", "django.db.backends.postgresql"])
        relacoes = [f for m in modelos_do_projeto() for f in m._meta.get_fields()
                    if isinstance(f, (models.ForeignKey, models.ManyToManyField))]
        self.assertGreaterEqual(len(modelos_do_projeto()), 8)
        self.assertGreaterEqual(len(relacoes), 10)
        self.assertTrue(any(isinstance(f, models.ManyToManyField) for f in relacoes))

    def test_interface_com_framework_css_responsiva_e_tema_claro_escuro(self):
        self.client.force_login(self.gestor)
        html = self.client.get(reverse("core:painel")).content.decode()
        self.assertIn("bootstrap", html)                                  # framework CSS
        self.assertIn('name="viewport"', html)                            # responsiva
        self.assertIn("navbar-toggler", html)                             # menu no celular
        self.assertIn("data-bs-theme", html)                              # tema claro/escuro
        self.assertIn('id="alternar-tema"', html)

    def test_organizacao_visual_consistente_em_todas_as_telas(self):
        """Todas as telas usam o mesmo layout (menu, alternância de tema e rodapé)."""
        self.client.force_login(self.gestor)
        produto = Produto.objects.filter(cozinha=self.gestor.cozinha).first()
        for url in [reverse("core:inicio"), reverse("core:painel"), reverse("estoque:produtos"),
                    reverse("estoque:produto", args=[produto.pk]), reverse("estoque:entrada"),
                    reverse("estoque:movimentacoes"), reverse("compras:listas"),
                    reverse("cozinhas:locais"), reverse("contas:perfil")]:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                for marca in ('class="navbar', 'id="alternar-tema"', "<footer"):
                    self.assertIn(marca, html)

    def test_admin_personalizado_com_tema_e_nao_o_padrao(self):
        self.assertIn("unfold", settings.INSTALLED_APPS)
        self.assertLess(settings.INSTALLED_APPS.index("unfold"),
                        settings.INSTALLED_APPS.index("django.contrib.admin"))
        from unfold.admin import ModelAdmin
        for modelo, model_admin in admin.site._registry.items():
            with self.subTest(modelo=modelo._meta.label):
                self.assertIsInstance(model_admin, ModelAdmin)
        self.client.force_login(self.admin)
        html = self.client.get(reverse("admin:index")).content.decode()
        self.assertIn("Guardião da Cozinha", html)
        self.assertNotIn("Django administration", html)
        self.assertNotIn("Administração do Django", html)

    def test_admin_personalizado_com_filtros(self):
        for modelo in modelos_do_projeto():
            if modelo in admin.site._registry:
                with self.subTest(modelo=modelo._meta.label):
                    self.assertTrue(admin.site._registry[modelo].list_filter)

    def test_autenticacao_por_usuario_e_senha(self):
        self.assertFalse(self.client.login(username="gestor1", password="senha-errada"))
        self.assertTrue(self.client.login(username="gestor1", password=SENHA))

    def test_documentacao_readme_com_secoes_obrigatorias(self):
        readme = (Path(settings.BASE_DIR) / "README.md").read_text(encoding="utf-8")
        secoes = {
            "nome da aplicação": r"^# .*Guardião da Cozinha",
            "integrantes do grupo": r"^## .*Integrantes",
            "descrição do projeto": r"^## .*Descrição",
            "tecnologias utilizadas": r"^## .*Tecnologias",
            "instruções para instalação": r"^## .*Instalação",
            "instruções para execução": r"^## .*Execução",
            "principais funcionalidades": r"^## .*funcionalidades",
            "estrutura do projeto": r"^## .*Estrutura do projeto",
        }
        for nome, padrao in secoes.items():
            with self.subTest(secao=nome):
                self.assertRegex(readme, re.compile(padrao, re.MULTILINE | re.IGNORECASE))
        for integrante in ("Gilson", "Luis", "Maria"):
            self.assertIn(integrante, readme)


class ControleDeVersaoTest(TestCase):
    """Git e GitHub: branches main, develop e feature e commits de cada integrante.

    Usa o repositório local; é pulado quando o projeto não está num clone git.
    """

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=settings.BASE_DIR, capture_output=True,
                              text=True).stdout

    def setUp(self):
        if not shutil.which("git") or not (Path(settings.BASE_DIR) / ".git").exists():
            self.skipTest("projeto fora de um repositório git")

    def test_branches_main_develop_feature(self):
        branches = self.git("branch", "-a", "--format=%(refname:short)")
        for nome in ("main", "develop", "feature"):
            with self.subTest(branch=nome):
                self.assertRegex(branches, rf"(^|/){nome}$|(^|/){nome}\n|(^|\n){nome}(\n|$)")

    def test_cada_integrante_com_pelo_menos_dois_commits(self):
        autores = self.git("log", "--all", "--no-merges", "--format=%an").lower().splitlines()
        for integrante in ("gilson", "luis", "maria"):
            with self.subTest(integrante=integrante):
                self.assertGreaterEqual(sum(integrante in a for a in autores), 2)


# ---------------------------------------------------------------------------
# 5.1 Checkpoint 1
# ---------------------------------------------------------------------------
class Checkpoint1Test(ComDadosDemo):
    def test_modelagem_completa_do_banco(self):
        """Toda tabela do projeto tem nome legível, ordenação e se liga a outra tabela."""
        for modelo in modelos_do_projeto():
            with self.subTest(modelo=modelo._meta.label):
                self.assertTrue(modelo._meta.verbose_name_plural)
                self.assertTrue(modelo._meta.ordering)
                ligacoes = [f for f in modelo._meta.get_fields() if f.is_relation]
                self.assertTrue(ligacoes)

    def test_ambiente_administrativo_configurado(self):
        """Todas as tabelas do projeto estão no admin e suas telas abrem."""
        self.client.force_login(self.admin)
        for modelo in modelos_do_projeto():
            if modelo._meta.model_name == "itemlistacompra":
                continue   # editado dentro da lista de compras (inline)
            with self.subTest(modelo=modelo._meta.label):
                self.assertIn(modelo, admin.site._registry)
                info = (modelo._meta.app_label, modelo._meta.model_name)
                self.assertEqual(self.client.get(reverse("admin:%s_%s_changelist" % info))
                                 .status_code, 200)
                self.assertEqual(self.client.get(reverse("admin:%s_%s_add" % info))
                                 .status_code, 200)

    def test_sistema_de_template_do_admin(self):
        """Painel do admin com template próprio (templates/admin/index.html) e indicadores."""
        self.assertTrue((Path(settings.BASE_DIR) / "templates/admin/index.html").exists())
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin:index"))
        self.assertIn("kpis", r.context)
        self.assertTemplateUsed(r, "admin/index.html")

    def test_diferentes_filtros_no_admin(self):
        self.client.force_login(self.admin)
        consultas = {
            "estoque_produto": ["nivel=BAIXO", "categoria__id__exact=1", "perecivel__exact=1"],
            "estoque_lote": ["situacao=VENCIDO", "local__tipo__exact=FREEZER"],
            "estoque_movimentacao": ["tipo__exact=SAIDA"],
            "compras_listacompra": ["status__exact=RASCUNHO"],
        }
        tipos = set()
        for tela, filtros in consultas.items():
            for filtro in filtros:
                with self.subTest(tela=tela, filtro=filtro):
                    r = self.client.get(reverse(f"admin:{tela}_changelist") + "?" + filtro)
                    self.assertEqual(r.status_code, 200)
            model_admin = admin.site._registry[apps.get_model(tela.replace("_", ".", 1))]
            for f in model_admin.list_filter:
                if isinstance(f, (tuple, list)):
                    tipos.add(f[1].__name__)          # campo com filtro do Unfold (faixa, lista)
                elif isinstance(f, type):
                    tipos.add("personalizado")        # SimpleListFilter próprio (filters.py)
                else:
                    tipos.add("campo")
        # filtros por campo, personalizados e de faixa de valores/datas
        self.assertIn("personalizado", tipos)
        self.assertTrue(any("Range" in t for t in tipos))
        self.assertGreaterEqual(len(tipos), 3)


# ---------------------------------------------------------------------------
# 5.2 Checkpoint 2
# ---------------------------------------------------------------------------
class Checkpoint2Test(ComDadosDemo):
    def test_login(self):
        self.assertContains(self.client.get(reverse("contas:login")), 'type="password"')
        r = self.client.post(reverse("contas:login"), {"username": "operador1", "password": SENHA})
        self.assertRedirects(r, reverse("core:painel"))

    def test_logout(self):
        self.client.force_login(self.operador)
        self.assertRedirects(self.client.post(reverse("contas:logout")), reverse("core:inicio"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_tela_de_cadastre_se(self):
        self.assertContains(self.client.get(reverse("contas:cadastro")), "Cadastre-se")
        r = self.client.post(reverse("contas:cadastro"), {
            "first_name": "Bia", "last_name": "Lima", "username": "bia",
            "email": "bia@exemplo.com", "password1": "Cozinha#2026", "password2": "Cozinha#2026",
            "nome_cozinha": "Casa da Bia", "tipo_cozinha": "DOMESTICA"})
        self.assertRedirects(r, reverse("core:painel"))
        self.assertTrue(Usuario.objects.filter(username="bia").exists())

    def test_banco_integrado_ao_ambiente_administrativo(self):
        """O que a área do usuário grava aparece no admin, e vice-versa."""
        self.client.force_login(self.gestor)
        self.client.post(reverse("estoque:produto_novo"), {
            "nome": "Integrado", "categoria": Categoria.objects.first().pk, "unidade": "un",
            "estoque_minimo": "1", "ativo": "on"})
        produto = Produto.objects.get(nome="Integrado")
        r = self.client.get(reverse("admin:estoque_produto_changelist") + "?q=Integrado")
        self.assertContains(r, "Integrado")
        Produto.objects.filter(pk=produto.pk).update(nome="Integrado pelo admin")
        r = self.client.get(reverse("estoque:produto", args=[produto.pk]))
        self.assertContains(r, "Integrado pelo admin")

    def test_framework_css_e_interface_amigavel(self):
        """Bootstrap, mensagens de retorno e erros de formulário destacados."""
        self.client.force_login(self.gestor)
        r = self.client.post(reverse("estoque:produto_novo"), {"nome": ""}, follow=True)
        html = r.content.decode()
        self.assertIn("bootstrap", html)
        self.assertIn("is-invalid", html)                 # campo com erro destacado
        self.assertIn("invalid-feedback", html)           # mensagem junto do campo
        lista = ListaCompra.objects.filter(cozinha=self.gestor.cozinha).first()
        r = self.client.post(reverse("compras:lista_excluir", args=[lista.pk]), follow=True)
        self.assertContains(r, "alert-success")           # retorno da ação

    def test_documentacao(self):
        readme = (Path(settings.BASE_DIR) / "README.md").read_text(encoding="utf-8")
        for trecho in ("Checkpoint 2", "cadastre-se", "runserver", "requirements.txt",
                       "popular_demo"):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho.lower(), readme.lower())
