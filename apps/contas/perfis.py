"""Perfis de acesso: cada perfil é um grupo do Django com permissões distintas.

Os grupos são criados/atualizados automaticamente após cada `migrate`
(sinal post_migrate em contas/apps.py), então o banco sempre reflete esta tabela.
"""
from django.contrib.auth.models import Group, Permission

V, A, C, D = "view", "add", "change", "delete"
TUDO = (V, A, C, D)

# modelo (app_label.model) -> ações permitidas
PERMISSOES = {
    "Administrador": None,   # None = todas as permissões do sistema
    "Gestor": {
        "cozinhas.cozinha": (V,),
        "cozinhas.localarmazenamento": TUDO,
        "estoque.categoria": (V, A, C),
        "estoque.fornecedor": (V, A, C),
        "estoque.produto": TUDO,
        "estoque.lote": (V, A, C),
        "estoque.movimentacao": (V, A),
        "compras.listacompra": TUDO,
        "compras.itemlistacompra": TUDO,
        "contas.usuario": (V,),
    },
    "Operador": {
        "cozinhas.localarmazenamento": (V,),
        "estoque.categoria": (V,),
        "estoque.produto": (V,),
        "estoque.lote": (V, A),
        "estoque.movimentacao": (V, A),
        "compras.listacompra": (V,),
        "compras.itemlistacompra": (V, C),
    },
}

GRUPO_DO_PERFIL = {"ADMIN": "Administrador", "GESTOR": "Gestor", "OPERADOR": "Operador"}


def configurar_grupos(**kwargs):
    for nome, regras in PERMISSOES.items():
        grupo, _ = Group.objects.get_or_create(name=nome)
        if regras is None:
            perms = Permission.objects.all()
        else:
            perms = []
            for modelo, acoes in regras.items():
                app_label, model = modelo.split(".")
                perms += Permission.objects.filter(
                    content_type__app_label=app_label, content_type__model=model,
                    codename__in=[f"{acao}_{model}" for acao in acoes])
        grupo.permissions.set(perms)


def sincronizar_grupo(usuario):
    """Mantém o usuário exatamente no grupo correspondente ao seu perfil."""
    nome = GRUPO_DO_PERFIL[usuario.perfil]
    grupo, _ = Group.objects.get_or_create(name=nome)
    outros = usuario.groups.filter(name__in=GRUPO_DO_PERFIL.values()).exclude(pk=grupo.pk)
    usuario.groups.remove(*outros)
    usuario.groups.add(grupo)
