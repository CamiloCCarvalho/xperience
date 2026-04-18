from django.urls import path
from app.views import admin, public, time_entry, user

urlpatterns = [

    # public routes
    path("", public.home, name="public-home"),
    path("register/", public.register, name="public-register"),
    path("login/", public.login_view, name="public-login"),
    path("logout/", public.logout_view, name="public-logout"),
    path("plataform/", public.plataform, name="public-plataform"),
    path("solutions/", public.solution, name="public-solutions"),
    path("resources/", public.resources, name="public-resources"),
    path("prices/", public.prices, name="public-prices"),
    path("contact/", public.contact, name="public-contact"),
    path("about/", public.about, name="public-about"),

    # user routes (membros da plataforma)
    path("user/workspaces/", user.user_workspaces, name="user-workspaces"),
    path("user/spaceon/home/", user.user_home, name="user-home"),
    path("user/spaceon/dashboard/", user.user_dashboard, name="user-dashboard"),
    path("user/spaceon/config/", user.user_config, name="user-config"),
    path("user/spaceon/account/", user.user_account, name="user-account"),
    path(
        "user/spaceon/time-entry/timer/draft/",
        time_entry.timer_active_draft,
        name="user-time-entry-timer-draft",
    ),
    path(
        "user/spaceon/time-entry/timer/start/",
        time_entry.timer_start,
        name="user-time-entry-timer-start",
    ),
    path(
        "user/spaceon/time-entry/timer/stop/",
        time_entry.timer_stop,
        name="user-time-entry-timer-stop",
    ),
    path(
        "user/spaceon/time-entry/timer/complete/",
        time_entry.timer_saved_complete_fields,
        name="user-time-entry-timer-complete",
    ),
    path(
        "user/spaceon/time-entry/timer/discard-pending/",
        time_entry.timer_discard_pending,
        name="user-time-entry-timer-discard-pending",
    ),
    path(
        "user/spaceon/time-entry/prepared-submit/",
        time_entry.prepared_entry_submit,
        name="user-time-entry-prepared-submit",
    ),
    path(
        "user/spaceon/time-entry/counts/",
        time_entry.time_entry_month_counts,
        name="user-time-entry-month-counts",
    ),
    path(
        "user/spaceon/time-entry/manual/create/",
        time_entry.manual_time_entry_create,
        name="user-time-entry-manual-create",
    ),
    path(
        "user/spaceon/time-entry/manual/<int:pk>/update/",
        time_entry.manual_time_entry_update,
        name="user-time-entry-manual-update",
    ),
    path(
        "user/spaceon/time-entry/manual/<int:pk>/delete/",
        time_entry.manual_time_entry_delete,
        name="user-time-entry-manual-delete",
    ),

    # admin routes (administrador da plataforma, não Django admin)
    path("user_admin/workspaces/", admin.admin_workspaces, name="admin-workspaces"),
    path("user_admin/workspaces/create/", admin.admin_workspaces_create, name="admin-workspaces-create"),
    path("user_admin/members/add/", admin.admin_members_add, name="admin-members-add"),
    path("user_admin/spaceon/home/", admin.admin_home, name="admin-home"),
    path("user_admin/spaceon/dashboard/", admin.admin_dashboard, name="admin-dashboard"),
    path("user_admin/spaceon/config/", admin.admin_config, name="admin-config"),
    path(
        "user_admin/spaceon/config/members/access/link-client/",
        admin.admin_config_member_link_client,
        name="admin-config-member-link-client",
    ),
    path(
        "user_admin/spaceon/config/members/access/unlink-client/",
        admin.admin_config_member_unlink_client,
        name="admin-config-member-unlink-client",
    ),
    path(
        "user_admin/spaceon/config/members/access/link-project/",
        admin.admin_config_member_link_project,
        name="admin-config-member-link-project",
    ),
    path(
        "user_admin/spaceon/config/members/access/unlink-project/",
        admin.admin_config_member_unlink_project,
        name="admin-config-member-unlink-project",
    ),
    path(
        "user_admin/spaceon/config/members/access/remove-membership/",
        admin.admin_config_member_remove_membership,
        name="admin-config-member-remove-membership",
    ),
    path("user_admin/spaceon/account/", admin.admin_account, name="admin-account"),
]
