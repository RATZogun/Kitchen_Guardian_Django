from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from .forms import CadastroForm, LoginForm, PerfilForm, SenhaForm


class EntrarView(LoginView):
    template_name = "contas/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


def cadastro(request):
    if request.user.is_authenticated:
        return redirect("core:painel")
    form = CadastroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        login(request, usuario)
        messages.success(request, f"Bem-vindo(a), {usuario.first_name}! Sua cozinha "
                                  f"“{usuario.cozinha}” foi criada com despensa, geladeira e freezer.")
        return redirect("core:painel")
    return render(request, "contas/cadastro.html", {"form": form})


@login_required
def perfil(request):
    form = PerfilForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Dados atualizados.")
        return redirect("contas:perfil")
    return render(request, "contas/perfil.html", {"form": form})


@login_required
def alterar_senha(request):
    form = SenhaForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        update_session_auth_hash(request, usuario)   # continua logado com a senha nova
        messages.success(request, "Senha alterada.")
        return redirect("contas:perfil")
    return render(request, "generico/form.html", {
        "form": form, "titulo": "Alterar senha", "voltar": "contas:perfil",
        "botao": "Alterar senha"})
