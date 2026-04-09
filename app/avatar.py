from django.contrib.auth.base_user import AbstractBaseUser

from utils.faker import fake_workspaces


def user_avatar_url(user: AbstractBaseUser) -> str:
    if user.is_authenticated and getattr(user, "avatar", None) and user.avatar.name:
        return user.avatar.url
    return fake_workspaces.make_user_avatar()["user_avatar_url"]


def workspace_avatar_url(workspace) -> str:
    if workspace.workspace_avatar and workspace.workspace_avatar.name:
        return workspace.workspace_avatar.url
    return fake_workspaces.make_workspace()["workspace_avatar"]["url"]
