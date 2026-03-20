"app/urls.py"

from django.urls import path
from app.views import public, user, admin

urlpatterns = [
    # public routes
    path("", public.home),
    path("plataform/", public.plataform),
    path("solutions/", public.solution),
    path("resources/", public.resources),
    path("prices/", public.prices),
    path("contact/", public.contact),
    path("about/", public.about),

    # user routes
    path("user/workspaces/", user.user_workspaces),
    path("user/spaceon/home/", user.user_home),
    path("user/spaceon/dashboard/", user.user_dashboard),
    path("user/spaceon/config/", user.user_config),
    path("user/spaceon/account/", user.user_account),

    # admin routes
    path("user_admin/workspaces/", admin.admin_workspaces),
    path("user_admin/workspaces/create/", admin.admin_workspaces_create),
    path("user_admin/spaceon/home/", admin.admin_home),
    path("user_admin/spaceon/dashboard/", admin.admin_dashboard),
    path("user_admin/spaceon/config/", admin.admin_config),
    path("user_admin/spaceon/account/", admin.admin_account),
]
