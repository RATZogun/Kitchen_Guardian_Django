"""Controle de acesso por cozinha no admin.

Administradores veem todas as cozinhas. Gestores veem e cadastram apenas
registros da própria cozinha: o filtro vale para as listagens, para as opções
dos campos de chave estrangeira e para o filtro lateral "cozinha".
"""

# Caminho até a cozinha a partir de cada modelo relacionado usado em formulários
CAMINHO_COZINHA = {
    "cozinha": "pk",
    "localarmazenamento": "cozinha",
    "produto": "cozinha",
    "lote": "produto__cozinha",
    "listacompra": "cozinha",
    "usuario": "cozinha",
}


def eh_admin_geral(request):
    return request.user.is_superuser or getattr(request.user, "eh_administrador", False)


class EscopoCozinhaMixin:
    #: lookup do modelo administrado até a cozinha (ex.: "produto__cozinha")
    campo_cozinha = "cozinha"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if eh_admin_geral(request):
            return qs
        return qs.filter(**{self.campo_cozinha: request.user.cozinha_id})

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        campo = super().formfield_for_foreignkey(db_field, request, **kwargs)
        caminho = CAMINHO_COZINHA.get(db_field.related_model._meta.model_name)
        if campo is not None and caminho and not eh_admin_geral(request):
            campo.queryset = campo.queryset.filter(**{caminho: request.user.cozinha_id})
            if db_field.name == "cozinha":
                campo.initial = request.user.cozinha_id
        return campo

    def get_list_filter(self, request):
        filtros = super().get_list_filter(request)
        if eh_admin_geral(request):
            return filtros
        # Para o gestor o filtro de cozinha não faz sentido: ele só tem uma
        return [f for f in filtros
                if (f[0] if isinstance(f, (tuple, list)) else f) != self.campo_cozinha]

    def get_list_display(self, request):
        colunas = super().get_list_display(request)
        if eh_admin_geral(request):
            return colunas
        return [c for c in colunas if c != "cozinha"]
