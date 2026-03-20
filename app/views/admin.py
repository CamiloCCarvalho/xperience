from django.shortcuts import render
from utils.xperience import workspaces

page_admin = "xperience/pages/admin/"
user_avatar_url = workspaces.make_user_avatar()['user_avatar_url']

# user routes
def admin_workspaces(request):
    return render(
        request,
        page_admin + "workspaces.html",
        context={
            "workspaces": [
                workspaces.make_workspace() for _ in range(10)
            ],
            "user_avatar_url": user_avatar_url
        }
    )

def admin_home(request):
    return render(
        request,
        page_admin + "home.html",
        context={
            "user_avatar_url": user_avatar_url
        }
    )

def admin_dashboard(request):
    return render(
        request,
        page_admin + "dashboard.html",
        context={
            "user_avatar_url": user_avatar_url
        }
    )

def admin_config(request):
    return render(
        request,
        page_admin + "configuration.html",
        context={
            "user_avatar_url": user_avatar_url
        }
    )

def admin_account(request):
    return render(
        request,
        page_admin + "account.html",
        context={
            "user_avatar_url": user_avatar_url
        }
    )

def admin_workspaces_create(request):
    return render(
        request,
        page_admin + "workspaces_create.html",
        context={
            "user_avatar_url": user_avatar_url
        }
    )