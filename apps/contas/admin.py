from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import (
    BooleanRadioFilter,
    ChoicesCheckboxFilter,
    RangeDateTimeFilter,
    RelatedDropdownFilter,
)
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.core.admin_mixins import EscopoCozinhaMixin

from .models import Usuario

admin.site.unregister(Group)


@admin.register(Usuario)
class UsuarioAdmin(EscopoCozinhaMixin, BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ["username", "nome_completo", "email", "perfil_badge", "cozinha",
                    "is_active", "last_login"]
    list_filter = [
        ("perfil", ChoicesCheckboxFilter),
        ("cozinha", RelatedDropdownFilter),
        ("is_active", BooleanRadioFilter),
        ("last_login", RangeDateTimeFilter),
        ("date_joined", RangeDateTimeFilter),
    ]
    list_filter_submit = True
    search_fields = ["username", "first_name", "last_name", "email"]
    ordering = ["first_name", "username"]

    fieldsets = [
        (None, {"fields": ["username", "password"]}),
        ("Dados pessoais", {"fields": ["first_name", "last_name", "email", "telefone"]}),
        ("Acesso ao sistema", {
            "fields": ["perfil", "cozinha", "is_active"],
            "description": "O perfil define as permissões: Administrador e Gestor entram "
                           "no admin; Operador usa apenas a área do usuário."}),
        ("Permissões avançadas", {"classes": ["collapse"],
                                  "fields": ["is_superuser", "groups", "user_permissions"]}),
        ("Datas", {"classes": ["collapse"], "fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"],
                "fields": ["username", "first_name", "last_name", "email", "perfil",
                           "cozinha", "password1", "password2"]}),
    ]
    readonly_fields = ["last_login", "date_joined"]

    @display(description="nome")
    def nome_completo(self, obj):
        return obj.get_full_name() or "—"

    @display(description="perfil", ordering="perfil",
             label={"Administrador": "danger", "Gestor": "warning", "Operador": "info"})
    def perfil_badge(self, obj):
        return obj.get_perfil_display()


@admin.register(Group)
class GrupoAdmin(BaseGroupAdmin, ModelAdmin):
    list_display = ["name", "total_permissoes", "total_usuarios"]

    @display(description="permissões")
    def total_permissoes(self, obj):
        return obj.permissions.count()

    @display(description="usuários")
    def total_usuarios(self, obj):
        return obj.user_set.count()
