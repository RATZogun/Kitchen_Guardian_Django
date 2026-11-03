from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ContasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.contas"
    verbose_name = "Acesso"

    def ready(self):
        from apps.contas.perfis import configurar_grupos
        post_migrate.connect(configurar_grupos, dispatch_uid="contas_configurar_grupos")
