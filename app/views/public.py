from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import authenticate
from django.shortcuts import redirect, render

from app.content.home import data_page_home
from app.forms import AdminRegisterForm, LoginForm
from app.models import User
from app.workspace_session import (
    clear_admin_workspace,
    clear_member_workspace,
    member_redirect_after_login,
)

page_public = "xperience/pages/public/"


def _post_login_redirect(request, user: User):
    if user.platform_role == User.PlatformRole.ADMIN:
        return redirect("admin-workspaces")
    return member_redirect_after_login(request, user)


def home(request):
    login_form = LoginForm(prefix="login")
    register_form = AdminRegisterForm(prefix="register")

    if request.method == "POST":
        form_kind = request.POST.get("form")
        if form_kind == "login":
            login_form = LoginForm(request.POST, prefix="login")
            if login_form.is_valid():
                email = login_form.cleaned_data["email"]
                password = login_form.cleaned_data["password"]
                user = authenticate(request, email=email, password=password)
                if user is not None:
                    login(request, user)
                    next_url = request.GET.get("next")
                    if next_url:
                        return redirect(next_url)
                    return _post_login_redirect(request, user)
                login_form.add_error(None, "Email ou senha inválidos.")
        elif form_kind == "register":
            register_form = AdminRegisterForm(request.POST, prefix="register")
            if register_form.is_valid():
                register_form.save()
                messages.success(
                    request,
                    "Administrador cadastrado. Entre com email e senha.",
                )
                return redirect("public-login")

    return render(
        request,
        page_public + "home.html",
        context={
            "data_page": data_page_home,
            "login_form": login_form,
            "register_form": register_form,
        },
    )


def register(request):
    if request.user.is_authenticated:
        return _post_login_redirect(request, request.user)
    if request.method == "POST":
        form = AdminRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Administrador cadastrado. Entre com email e senha.",
            )
            return redirect("public-login")
    else:
        form = AdminRegisterForm()
    return render(
        request,
        page_public + "register.html",
        context={"form": form},
    )


def login_view(request):
    if request.user.is_authenticated:
        return _post_login_redirect(request, request.user)
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            user = authenticate(request, email=email, password=password)
            if user is not None:
                login(request, user)
                next_url = request.GET.get("next")
                if next_url:
                    return redirect(next_url)
                return _post_login_redirect(request, user)
            form.add_error(None, "Email ou senha inválidos.")
    else:
        form = LoginForm()
    return render(
        request,
        page_public + "login.html",
        context={"form": form},
    )


def logout_view(request):
    clear_member_workspace(request)
    clear_admin_workspace(request)
    logout(request)
    messages.info(request, "Você saiu da conta.")
    return redirect("public-home")


def plataform(request):
    return render(request, page_public + "plataform.html")


def solution(request):
    return render(request, page_public + "solutions.html")


def resources(request):
    return render(request, page_public + "resources.html")


def prices(request):
    return render(request, page_public + "prices.html")


def contact(request):
    return render(request, page_public + "contact.html")


def about(request):
    return render(request, page_public + "about.html")
