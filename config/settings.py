"""
Configurações do projeto Guardião da Cozinha.

Valores sensíveis vêm de variáveis de ambiente (veja .env.example). Os padrões
abaixo servem apenas para desenvolvimento local.
"""
import os
from pathlib import Path

from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent


def _carregar_env(caminho):
    """Lê um arquivo .env simples (CHAVE=valor) sem depender de bibliotecas externas."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


_carregar_env(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-inseguro-troque-em-producao")
DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")


# ---------------------------------------------------------------------------
# Aplicações
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Tema do admin (precisa vir antes de django.contrib.admin)
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Apps do projeto
    "apps.core",
    "apps.contas",
    "apps.cozinhas",
    "apps.estoque",
    "apps.compras",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ---------------------------------------------------------------------------
# Banco de dados relacional
# SQLite por padrão; PostgreSQL se DB_ENGINE=postgresql estiver no .env.
# ---------------------------------------------------------------------------
if os.getenv("DB_ENGINE") == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "guardiao_da_cozinha"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "localhost"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "contas.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "admin:login"
LOGIN_REDIRECT_URL = "admin:index"   # área do usuário entra no Checkpoint 2
LOGOUT_REDIRECT_URL = "core:inicio"


# ---------------------------------------------------------------------------
# Internacionalização
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Regras de negócio
DIAS_ALERTA_VALIDADE = 7   # RF015: limiar padrão de "vence em breve"


# ---------------------------------------------------------------------------
# Tema do admin: Unfold
# ---------------------------------------------------------------------------
def _perm(codename):
    """Mostra o item da barra lateral só para quem tem a permissão."""
    return lambda request: request.user.has_perm(codename)


UNFOLD = {
    "SITE_TITLE": "Guardião da Cozinha",
    "SITE_HEADER": "Guardião da Cozinha",
    "SITE_SUBHEADER": "Administração do estoque",
    "SITE_SYMBOL": "kitchen",
    "SITE_URL": "/",
    "SITE_FAVICONS": [
        {"rel": "icon", "sizes": "any", "type": "image/svg+xml",
         "href": lambda request: static("img/favicon.svg")},
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
    "ENVIRONMENT": "apps.core.dashboard.ambiente",
    "DASHBOARD_CALLBACK": "apps.core.dashboard.dashboard_callback",
    "LOGIN": {
        "image": lambda request: static("img/login.svg"),
    },
    "BORDER_RADIUS": "8px",
    "COLORS": {
        # Verde-oliva: remete a cozinha/alimentos e contrasta bem nos dois temas
        "primary": {
            "50": "oklch(98.2% .018 135)",
            "100": "oklch(96.2% .044 135)",
            "200": "oklch(92.5% .084 135)",
            "300": "oklch(87.1% .136 135)",
            "400": "oklch(79.2% .175 135)",
            "500": "oklch(68.1% .162 140)",
            "600": "oklch(57.5% .138 142)",
            "700": "oklch(47.8% .112 143)",
            "800": "oklch(40.4% .089 143)",
            "900": "oklch(35.2% .073 144)",
            "950": "oklch(25.5% .055 145)",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Visão geral"),
                "items": [
                    {"title": _("Painel"), "icon": "dashboard",
                     "link": reverse_lazy("admin:index")},
                ],
            },
            {
                "title": _("Estoque"),
                "separator": True,
                "collapsible": False,
                "items": [
                    {"title": _("Produtos"), "icon": "inventory_2",
                     "link": reverse_lazy("admin:estoque_produto_changelist"),
                     "badge": "apps.core.dashboard.badge_abaixo_minimo",
                     "permission": _perm("estoque.view_produto")},
                    {"title": _("Lotes"), "icon": "deployed_code",
                     "link": reverse_lazy("admin:estoque_lote_changelist"),
                     "badge": "apps.core.dashboard.badge_lotes_em_risco",
                     "permission": _perm("estoque.view_lote")},
                    {"title": _("Movimentações"), "icon": "swap_vert",
                     "link": reverse_lazy("admin:estoque_movimentacao_changelist"),
                     "permission": _perm("estoque.view_movimentacao")},
                    {"title": _("Categorias"), "icon": "category",
                     "link": reverse_lazy("admin:estoque_categoria_changelist"),
                     "permission": _perm("estoque.view_categoria")},
                    {"title": _("Fornecedores"), "icon": "local_shipping",
                     "link": reverse_lazy("admin:estoque_fornecedor_changelist"),
                     "permission": _perm("estoque.view_fornecedor")},
                ],
            },
            {
                "title": _("Compras"),
                "separator": True,
                "items": [
                    {"title": _("Listas de compras"), "icon": "shopping_cart",
                     "link": reverse_lazy("admin:compras_listacompra_changelist"),
                     "permission": _perm("compras.view_listacompra")},
                ],
            },
            {
                "title": _("Cozinhas"),
                "separator": True,
                "items": [
                    {"title": _("Cozinhas"), "icon": "skillet",
                     "link": reverse_lazy("admin:cozinhas_cozinha_changelist"),
                     "permission": _perm("cozinhas.view_cozinha")},
                    {"title": _("Locais de armazenamento"), "icon": "kitchen",
                     "link": reverse_lazy("admin:cozinhas_localarmazenamento_changelist"),
                     "permission": _perm("cozinhas.view_localarmazenamento")},
                ],
            },
            {
                "title": _("Acesso"),
                "separator": True,
                "items": [
                    {"title": _("Usuários"), "icon": "person",
                     "link": reverse_lazy("admin:contas_usuario_changelist"),
                     "permission": _perm("contas.view_usuario")},
                    {"title": _("Perfis (grupos)"), "icon": "group",
                     "link": reverse_lazy("admin:auth_group_changelist"),
                     "permission": _perm("auth.view_group")},
                ],
            },
        ],
    },
}
