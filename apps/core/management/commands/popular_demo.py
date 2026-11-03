"""Popula o banco com dados de demonstração (cozinhas, produtos, lotes, movimentações).

    python manage.py popular_demo            # só popula se o banco estiver vazio
    python manage.py popular_demo --limpar   # apaga os dados de estoque e recria

As movimentações passam pelas mesmas regras de negócio do sistema (services.py),
então os saldos ficam coerentes com o histórico.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.compras.models import ItemListaCompra, ListaCompra
from apps.contas.models import Usuario
from apps.cozinhas.models import Cozinha, LocalArmazenamento
from apps.estoque import services
from apps.estoque.models import Categoria, Fornecedor, Lote, Movimentacao, Produto, hoje

SENHA_DEMO = "guardiao123"

CATEGORIAS = [
    ("Grãos e cereais", "Arroz, feijão, farinhas e massas", "#a16207"),
    ("Hortifruti", "Frutas, verduras e legumes frescos", "#16a34a"),
    ("Laticínios", "Leite, queijos, iogurtes e manteiga", "#0ea5e9"),
    ("Carnes e ovos", "Carnes bovinas, aves, peixes e ovos", "#dc2626"),
    ("Mercearia", "Óleos, temperos, enlatados e açúcar", "#9333ea"),
    ("Bebidas", "Sucos, café e água", "#f59e0b"),
    ("Limpeza", "Produtos de limpeza da cozinha", "#64748b"),
    ("Congelados", "Polpas, vegetais e pratos congelados", "#2563eb"),
]

FORNECEDORES = [
    ("Atacadão Sul de Minas", "12.345.678/0001-90", "(35) 3821-1000",
     ["Grãos e cereais", "Mercearia", "Bebidas", "Limpeza"]),
    ("Ceasa Lavras Hortifruti", "23.456.789/0001-01", "(35) 3822-2000", ["Hortifruti"]),
    ("Laticínios Serra Verde", "34.567.890/0001-12", "(35) 3823-3000", ["Laticínios"]),
    ("Frigorífico Campo Belo", "45.678.901/0001-23", "(35) 3832-4000",
     ["Carnes e ovos", "Congelados"]),
    ("Distribuidora Mineira", "56.789.012/0001-34", "(35) 3824-5000",
     ["Mercearia", "Bebidas", "Congelados"]),
]

# nome, categoria, unidade, mínimo, perecível, tipo de local, validade (dias), compra típica
PRODUTOS = [
    ("Arroz tipo 1", "Grãos e cereais", "kg", 20, True, "DESPENSA", 365, 50),
    ("Feijão carioca", "Grãos e cereais", "kg", 15, True, "DESPENSA", 180, 30),
    ("Macarrão espaguete", "Grãos e cereais", "kg", 8, True, "DESPENSA", 365, 20),
    ("Farinha de trigo", "Grãos e cereais", "kg", 5, True, "DESPENSA", 120, 10),
    ("Tomate", "Hortifruti", "kg", 6, True, "GELADEIRA", 7, 12),
    ("Alface crespa", "Hortifruti", "un", 10, True, "GELADEIRA", 5, 20),
    ("Batata inglesa", "Hortifruti", "kg", 10, True, "DESPENSA", 20, 25),
    ("Banana prata", "Hortifruti", "kg", 5, True, "DESPENSA", 6, 10),
    ("Leite integral", "Laticínios", "l", 12, True, "GELADEIRA", 10, 24),
    ("Queijo muçarela", "Laticínios", "kg", 2, True, "GELADEIRA", 25, 5),
    ("Manteiga", "Laticínios", "g", 500, True, "GELADEIRA", 60, 1000),
    ("Peito de frango", "Carnes e ovos", "kg", 10, True, "FREEZER", 90, 20),
    ("Carne moída", "Carnes e ovos", "kg", 8, True, "FREEZER", 60, 15),
    ("Ovos", "Carnes e ovos", "un", 60, True, "GELADEIRA", 21, 120),
    ("Óleo de soja", "Mercearia", "l", 6, True, "DESPENSA", 300, 12),
    ("Sal refinado", "Mercearia", "kg", 2, False, "DESPENSA", 0, 5),
    ("Açúcar cristal", "Mercearia", "kg", 5, False, "DESPENSA", 0, 10),
    ("Café torrado", "Bebidas", "g", 1000, True, "DESPENSA", 150, 2000),
    ("Detergente neutro", "Limpeza", "ml", 2000, False, "DESPENSA", 0, 5000),
    ("Polpa de maracujá", "Congelados", "kg", 3, True, "FREEZER", 120, 6),
]

COZINHAS = [
    # nome, tipo, cidade, refeições/dia, escala das quantidades, locais
    ("Restaurante Universitário", Cozinha.Tipo.INSTITUCIONAL, "Lavras", 1800, 6,
     [("Despensa central", "DESPENSA", None, None), ("Câmara fria", "GELADEIRA", 0, 4),
      ("Freezer 1", "FREEZER", -20, -16)]),
    ("Cantina Sabor Mineiro", Cozinha.Tipo.COMERCIAL, "Lavras", 150, 2,
     [("Estoque seco", "DESPENSA", None, None), ("Geladeira industrial", "GELADEIRA", 2, 6),
      ("Freezer horizontal", "FREEZER", -18, -12)]),
    ("Casa da Família Souza", Cozinha.Tipo.DOMESTICA, "Perdões", 4, Decimal("0.25"),
     [("Armário", "DESPENSA", None, None), ("Geladeira", "GELADEIRA", 3, 7),
      ("Congelador", "FREEZER", -18, -10)]),
]


def custo_unitario(unidade):
    """Custo plausível por unidade de medida (g e ml custam centavos)."""
    faixa = {"g": (.02, .08), "ml": (.005, .02), "un": (.5, 3)}.get(unidade, (4, 40))
    return Decimal(random.uniform(*faixa)).quantize(Decimal("0.01"))


class Command(BaseCommand):
    help = "Popula o banco com dados de demonstração."

    def add_arguments(self, parser):
        parser.add_argument("--limpar", action="store_true",
                            help="Apaga cozinhas, estoque e compras antes de popular.")
        parser.add_argument("--semente", type=int, default=42)

    @transaction.atomic
    def handle(self, *args, limpar=False, semente=42, **options):
        random.seed(semente)
        if limpar:
            self._limpar()
        elif Cozinha.objects.exists():
            self.stdout.write(self.style.WARNING(
                "O banco já tem dados. Use --limpar para recriar."))
            return

        admin = self._usuario("admin", "Ana", "Administradora", Usuario.Perfil.ADMINISTRADOR,
                              None, superuser=True)
        categorias = {nome: Categoria.objects.create(nome=nome, descricao=desc, cor=cor)
                      for nome, desc, cor in CATEGORIAS}
        fornecedores = []
        for nome, cnpj, tel, cats in FORNECEDORES:
            f = Fornecedor.objects.create(nome=nome, cnpj=cnpj, telefone=tel,
                                          email=f"vendas@{nome.split()[0].lower()}.com.br")
            f.categorias.set([categorias[c] for c in cats])
            fornecedores.append(f)

        usuarios = [admin]
        for i, (nome, tipo, cidade, refeicoes, escala, locais) in enumerate(COZINHAS, 1):
            cozinha = Cozinha.objects.create(nome=nome, tipo=tipo, cidade=cidade,
                                             refeicoes_por_dia=refeicoes,
                                             endereco=f"Rua Exemplo, {100 * i}")
            locais_por_tipo = {}
            for nome_local, tipo_local, tmin, tmax in locais:
                locais_por_tipo[tipo_local] = LocalArmazenamento.objects.create(
                    cozinha=cozinha, nome=nome_local, tipo=tipo_local,
                    temperatura_min=tmin, temperatura_max=tmax)
            gestor = self._usuario(f"gestor{i}", ["Bruno", "Carla", "Diego"][i - 1], "Gestor",
                                   Usuario.Perfil.GESTOR, cozinha)
            operador = self._usuario(f"operador{i}", ["Elisa", "Fábio", "Gabi"][i - 1],
                                     "Operador", Usuario.Perfil.OPERADOR, cozinha)
            cozinha.responsavel = gestor
            cozinha.save()
            usuarios += [gestor, operador]
            self._estoque(cozinha, Decimal(escala), categorias, fornecedores, locais_por_tipo,
                          gestor, operador)

        self._lista_compras()
        self.stdout.write(self.style.SUCCESS(
            f"Pronto: {Cozinha.objects.count()} cozinhas, {Produto.objects.count()} produtos, "
            f"{Lote.objects.count()} lotes, {Movimentacao.objects.count()} movimentações."))
        self.stdout.write("Usuários (senha para todos: %s):" % SENHA_DEMO)
        for u in usuarios:
            self.stdout.write(f"  {u.username:<10} {u.get_perfil_display():<14} {u.cozinha or '-'}")

    # ------------------------------------------------------------------
    def _limpar(self):
        Movimentacao.objects.all().delete()
        ItemListaCompra.objects.all().delete()
        ListaCompra.objects.all().delete()
        Lote.objects.all().delete()
        Produto.objects.all().delete()
        Fornecedor.objects.all().delete()
        Categoria.objects.all().delete()
        Usuario.objects.filter(username__in=["admin"] + [f"{p}{i}" for p in ("gestor", "operador")
                                                         for i in (1, 2, 3)]).delete()
        LocalArmazenamento.objects.all().delete()
        Cozinha.objects.all().delete()

    def _usuario(self, username, nome, sobrenome, perfil, cozinha, superuser=False):
        u = Usuario(username=username, first_name=nome, last_name=sobrenome, perfil=perfil,
                    cozinha=cozinha, email=f"{username}@guardiao.local", is_superuser=superuser)
        u.set_password(SENHA_DEMO)
        u.save()
        return u

    def _estoque(self, cozinha, escala, categorias, fornecedores, locais, gestor, operador):
        def q(valor):   # quantidade escalada para o tamanho da cozinha, mínimo 1
            return max(Decimal(valor) * escala, Decimal("1")).quantize(Decimal("1"))

        for nome, cat, unidade, minimo, perecivel, tipo_local, vida, compra in PRODUTOS:
            fornecedor = next((f for f in fornecedores
                               if f.categorias.filter(nome=cat).exists()), None)
            produto = Produto.objects.create(
                cozinha=cozinha, nome=nome, categoria=categorias[cat], unidade=unidade,
                estoque_minimo=q(minimo), perecivel=perecivel, fornecedor_padrao=fornecedor,
                criado_por=gestor)

            # 1 a 3 entradas nos últimos 45 dias
            for _ in range(random.randint(1, 3)):
                entrada = hoje() - timedelta(days=random.randint(0, 45))
                validade = None
                if perecivel:
                    validade = entrada + timedelta(days=max(1, int(vida * random.uniform(.5, 1.1))))
                lote = Lote(produto=produto, local=locais[tipo_local], fornecedor=fornecedor,
                            codigo=f"L{random.randint(1000, 9999)}",
                            quantidade_inicial=q(compra * random.uniform(.6, 1.2)),
                            data_entrada=entrada, data_validade=validade,
                            custo_unitario=custo_unitario(unidade))
                services.registrar_entrada(lote, random.choice([gestor, operador]))
                self._consumir(lote, operador, gestor)

    def _consumir(self, lote, operador, gestor):
        """Gera saídas ao longo dos dias e descarta parte dos vencidos."""
        dias = (hoje() - lote.data_entrada).days
        for _ in range(random.randint(0, min(dias, 6))):
            lote.refresh_from_db()
            if lote.quantidade_atual <= 0:
                break
            data = lote.data_entrada + timedelta(days=random.randint(0, dias))
            if lote.data_validade and data > lote.data_validade:
                continue
            qtd = (lote.quantidade_atual * Decimal(random.uniform(.1, .45))).quantize(Decimal("1"))
            if qtd >= 1:
                services.registrar_baixa(lote, qtd, operador, data=data,
                                         motivo=Movimentacao.Motivo.PREPARO)
        lote.refresh_from_db()
        if lote.situacao == "VENCIDO" and random.random() < .5:
            services.registrar_baixa(lote, lote.quantidade_atual, gestor,
                                     tipo=Movimentacao.Tipo.DESCARTE,
                                     motivo=Movimentacao.Motivo.VENCIMENTO,
                                     observacao="Descarte na conferência semanal")

    def _lista_compras(self):
        for cozinha in Cozinha.objects.all():
            faltando = Produto.objects.abaixo_do_minimo().filter(cozinha=cozinha)[:6]
            if not faltando:
                continue
            lista = ListaCompra.objects.create(
                cozinha=cozinha, titulo="Reposição semanal", criada_por=cozinha.responsavel,
                data_prevista=hoje() + timedelta(days=2))
            for p in faltando:
                ItemListaCompra.objects.create(
                    lista=lista, produto=p, fornecedor=p.fornecedor_padrao,
                    quantidade=max(2 * p.estoque_minimo - p.saldo, Decimal("1")),
                    preco_estimado=Decimal(random.uniform(3, 35)).quantize(Decimal("0.01")),
                    comprado=random.random() < .3)
