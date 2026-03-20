from django.shortcuts import render
from utils.xperience import workspaces

page_user = "xperience/pages/user/"
user_avatar_url = workspaces.make_user_avatar()['user_avatar_url']

# user routes
def user_workspaces(request):
    return render(
        request,
        page_user + "workspaces.html",
        context={
            "workspaces": [
                workspaces.make_workspace() for _ in range(10)
            ],
            "user_avatar_url": user_avatar_url
        }
    )

def user_home(request):
    return render(
        request,
        page_user + "home.html",
        context={
            "user_avatar_url": user_avatar_url
        }
    )

def user_dashboard(request):
    return render(
        request,
        page_user + "dashboard.html",
        context={
            "user_avatar_url": user_avatar_url
        }
    )

def user_config(request):
    return render(
        request,
        page_user + "configuration.html",
        context={
            "user_avatar_url": user_avatar_url
        }
    )

def user_account(request):
    return render(
        request,
        page_user + "account.html",
        context={
            "user_avatar_url": user_avatar_url
        }
    )