from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import authenticate
from django.shortcuts import redirect, render

from app.content.home import data_page_home
from app.forms import AdminRegisterForm, LoginForm
from app.models import User, PaymentMethod
import hashlib
from datetime import datetime
from django.contrib.auth.hashers import make_password
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
    # Admin autenticado nunca permanece na home pública: vai direto pro painel.
    # (defesa em profundidade: a logo do admin já aponta pra admin-workspaces,
    # mas qualquer link/bookmark que caia em "/" também redireciona.)
    if (
        request.user.is_authenticated
        and isinstance(request.user, User)
        and request.user.platform_role == User.PlatformRole.ADMIN
    ):
        return redirect("admin-workspaces")

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
    """Cadastro simples de administrador (sem plano/pagamento).

    Independente da sessão: nunca redireciona usuários autenticados pra fora.
    Cada GET abre form limpo; cada POST tenta criar um NOVO admin.
    Diferente do register_admin_plan, esta view NÃO faz auto-login —
    o novo admin precisa logar manualmente em /login/.
    """
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


def register_admin_plan(request):
    """Cadastro de administrador (com plano e pagamento).

    A view é INDEPENDENTE da sessão: nunca redireciona um usuário já
    autenticado pra fora. Cada request abre formulário limpo no GET
    (sem reaproveitar dados do usuário logado), e cada POST tenta
    criar um NOVO admin — independente de quem está logado.
    """
    if request.method == "POST":
        form = AdminRegisterForm(request.POST)
        if form.is_valid():
            # cria o usuário administrador
            user = form.save()

            # extrai dados de pagamento do POST (não armazenar CVV/numero completo)
            number = request.POST.get("number_credit_card", "").strip()
            cvv = request.POST.get("cvv", "").strip()
            expiry = request.POST.get("expiry_date", "").strip()  # esperado MM/YY ou MM/YYYY
            holder = request.POST.get("titular_name", "").strip()
            cpf = request.POST.get("cpf", "").strip()
            plan = request.POST.get("plan", "")

            # gerar token simples (placeholder) — não é substituto de tokenização PCI
            token_source = f"{number}|{cvv}|{datetime.utcnow().isoformat()}"
            token = hashlib.sha256(token_source.encode("utf-8")).hexdigest()

            # máscara do CPF e últimos 4 do cartão
            card_last4 = number[-4:] if len(number) >= 4 else ""
            cpf_masked = None
            if cpf:
                cleaned = ''.join(ch for ch in cpf if ch.isdigit())
                if len(cleaned) > 4:
                    cpf_masked = f"***.***.{cleaned[-3:]}"
                else:
                    cpf_masked = cleaned

            # parse expiry
            expiry_month = None
            expiry_year = None
            if expiry:
                parts = expiry.replace('/', '').strip()
                if len(parts) == 4:  # MMYY
                    expiry_month = int(parts[:2])
                    year = int(parts[2:])
                    expiry_year = 2000 + year if year < 100 else year
                elif len(parts) == 6:  # MMYYYY
                    expiry_month = int(parts[:2])
                    expiry_year = int(parts[2:])

            PaymentMethod.objects.create(
                user=user,
                token=token,
                holder_name=holder,
                card_last4=card_last4,
                expiry_month=expiry_month,
                expiry_year=expiry_year,
                cpf_masked=cpf_masked or "",
                plan=plan or "",
            )

            # também grava resumo no próprio User (hash nativa do Django)
            if number:
                try:
                    cleaned_number = "".join(ch for ch in number if ch.isdigit())
                    user.card_last4 = cleaned_number[-4:]
                    user.card_holder_name = holder or ""
                    user.card_expiry_month = expiry_month
                    user.card_expiry_year = expiry_year
                    user.card_hash = make_password(cleaned_number)
                    user.save(update_fields=[
                        "card_hash",
                        "card_last4",
                        "card_holder_name",
                        "card_expiry_month",
                        "card_expiry_year",
                    ])
                except Exception:
                    # não falhar o fluxo principal por erro no armazenamento de cartão
                    pass

            # Limpa qualquer sessão pré-existente antes de autenticar como o novo
            # admin. Isso garante que cadastros sucessivos NÃO confundam contexto:
            # se um admin A estava logado e cadastrou admin B, a sessão vira B,
            # nunca um híbrido. Sem este logout, futuras visitas à página de
            # cadastro herdariam estado da sessão anterior.
            if request.user.is_authenticated:
                clear_admin_workspace(request)
                clear_member_workspace(request)
                logout(request)
            login(request, user)
            return _post_login_redirect(request, user)
        # se inválido, render com erros
        return render(request, page_public + "register_admin_plan.html", {"form": form})

    # GET
    form = AdminRegisterForm()
    return render(request, page_public + "register_admin_plan.html", {"form": form})

