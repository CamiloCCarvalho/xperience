from django.contrib import admin

from .models import (
    Department,
    TimeEntry,
    TimeEntryTemplate,
    User,
    UserDepartment,
    WorkSchedule,
    Workspace,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    ordering = ("-created_at",)
    list_display = ("email", "first_name", "platform_role", "is_staff", "is_active")
    list_filter = ("platform_role", "is_staff", "is_active")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")
    filter_horizontal = ("groups", "user_permissions")
    fieldsets = (
        (None, {"fields": ("email",)}),
        ("Plataforma", {"fields": ("platform_role",)}),
        ("Perfil", {"fields": ("first_name", "last_name", "avatar")}),
        (
            "Permissões Django",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (
            "Estado da conta",
            {"fields": ("is_verified", "is_deleted", "is_locked", "is_expired", "is_inactive")},
        ),
        ("Datas", {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("workspace_name", "owner", "created_at")
    search_fields = ("workspace_name", "owner__email")


@admin.register(WorkSchedule)
class WorkScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "expected_hours_per_day", "has_fixed_days")
    list_filter = ("workspace",)


@admin.register(TimeEntryTemplate)
class TimeEntryTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "workspace",
        "use_client",
        "use_project",
        "use_task",
        "use_type",
        "use_description",
    )
    list_filter = ("workspace",)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "schedule", "template")
    list_filter = ("workspace",)


@admin.register(UserDepartment)
class UserDepartmentAdmin(admin.ModelAdmin):
    list_display = ("user", "workspace", "department")
    list_filter = ("workspace",)


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "workspace", "department", "date", "hours")
    list_filter = ("workspace", "department")
    date_hierarchy = "date"
