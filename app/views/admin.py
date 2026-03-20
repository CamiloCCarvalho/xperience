from django.shortcuts import render
from utils.faker import fake_workspaces, fake_user

page_admin = "xperience/pages/admin/"
user_avatar_url = fake_workspaces.make_user_avatar()['user_avatar_url']

# user routes
def admin_workspaces(request, id):
    return render(
        request,
        page_admin + "workspaces.html",
        context={
            "user_data": fake_user.make_user_data(),
            "workspaces": [
                fake_workspaces.make_workspace() for _ in range(10)
            ],
            "user_avatar_url": user_avatar_url
        }
    )

def admin_home(request, id):
    return render(
        request,
        page_admin + "home.html",
        context={
            "user_data": fake_user.make_user_data(),
            "user_avatar_url": user_avatar_url
        }
    )

def admin_dashboard(request, id):
    return render(
        request,
        page_admin + "dashboard.html",
        context={
            "user_data": fake_user.make_user_data(),
            "user_avatar_url": user_avatar_url
        }
    )

def admin_config(request, id):
    return render(
        request,
        page_admin + "configuration.html",
        context={
            "user_data": fake_user.make_user_data(),
            "user_avatar_url": user_avatar_url
        }
    )

def admin_account(request, id):
    return render(
        request,
        page_admin + "account.html",
        context={
            "user_data": fake_user.make_user_data(),
            "user_avatar_url": user_avatar_url
        }
    )

def admin_workspaces_create(request, id):
    return render(
        request,
        page_admin + "workspaces_create.html",
        context={
            "user_data": fake_user.make_user_data(),
            "user_avatar_url": user_avatar_url
        }
    )