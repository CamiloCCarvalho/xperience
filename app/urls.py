"app/urls.py"

from django.urls import path
from app.views import public, user, admin

urlpatterns = [
    # public routes
    path("", public.home, name="public-home"),
    path("plataform/", public.plataform, name="public-plataform"),
    path("solutions/", public.solution, name="public-solutions"),
    path("resources/", public.resources, name="public-resources"),
    path("prices/", public.prices, name="public-prices"),
    path("contact/", public.contact, name="public-contact"),
    path("about/", public.about, name="public-about"),
    # user routes
    path("user/workspaces/", user.user_workspaces, name="user-workspaces"),
    path("user/spaceon/home/", user.user_home, name="user-home"),
    path("user/spaceon/dashboard/", user.user_dashboard, name="user-dashboard"),
    path("user/spaceon/config/", user.user_config, name="user-config"),
    path("user/spaceon/account/", user.user_account, name="user-account"),
    # admin routes
    path("user_admin/<int:id>/workspaces/", admin.admin_workspaces, name="admin-workspaces"),
    path("user_admin/<int:id>/workspaces/create/", admin.admin_workspaces_create, name="admin-workspaces-create"),
    path("user_admin/<int:id>/spaceon/home/", admin.admin_home, name="admin-home"),
    path("user_admin/<int:id>/spaceon/dashboard/", admin.admin_dashboard, name="admin-dashboard"),
    path("user_admin/<int:id>/spaceon/config/", admin.admin_config, name="admin-config"),
    path("user_admin/<int:id>/spaceon/account/", admin.admin_account, name="admin-account"),
]
