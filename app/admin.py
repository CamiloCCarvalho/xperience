from django.contrib import admin

from .models import (
    Client,
    CompensationHistory,
    Department,
    EmployeeProfile,
    JobHistory,
    Project,
    Task,
    TimeEntry,
    TimeEntryTemplate,
    User,
    UserClient,
    UserDepartment,
    UserProject,
    WorkSchedule,
    Workspace,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    ordering = ("-created_at",)
    list_display = ("email", "first_name", "platform_role", "platform_join_date", "is_staff", "is_active")
    list_filter = ("platform_role", "is_staff", "is_active")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")
    filter_horizontal = ("groups", "user_permissions")
    fieldsets = (
        (None, {"fields": ("email",)}),
        ("Plataforma", {"fields": ("platform_role",)}),
        ("Perfil", {"fields": ("first_name", "last_name", "avatar", "birth_date", "platform_join_date")}),
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
    search_fields = ("name", "workspace__workspace_name")


@admin.register(UserDepartment)
class UserDepartmentAdmin(admin.ModelAdmin):
    list_display = ("user", "workspace", "department")
    list_filter = ("workspace",)


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "workspace",
        "employment_status",
        "hire_date",
        "termination_date",
        "current_job_title",
    )
    list_filter = ("workspace", "employment_status")
    search_fields = ("user__email", "workspace__workspace_name", "current_job_title")
    autocomplete_fields = ("user", "workspace")


@admin.register(JobHistory)
class JobHistoryAdmin(admin.ModelAdmin):
    list_display = ("employee_profile", "job_title", "start_date", "end_date")
    list_filter = ("employee_profile__workspace",)
    search_fields = ("employee_profile__user__email", "job_title")
    autocomplete_fields = ("employee_profile",)


@admin.register(CompensationHistory)
class CompensationHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "employee_profile",
        "compensation_type",
        "monthly_salary",
        "hourly_rate",
        "start_date",
        "end_date",
    )
    list_filter = ("employee_profile__workspace", "compensation_type")
    search_fields = ("employee_profile__user__email",)
    autocomplete_fields = ("employee_profile",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "is_active", "created_at", "created_by")
    list_filter = ("workspace", "is_active")
    search_fields = ("name", "document", "email")
    autocomplete_fields = ("workspace", "created_by")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "workspace", "is_active", "created_at")
    list_filter = ("workspace", "is_active")
    search_fields = ("name", "client__name")
    autocomplete_fields = ("workspace", "client", "created_by")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "is_active")
    list_filter = ("is_active", "project__workspace")
    search_fields = ("name", "project__name")
    autocomplete_fields = ("project",)


@admin.register(UserClient)
class UserClientAdmin(admin.ModelAdmin):
    list_display = ("user", "client", "workspace")
    list_filter = ("workspace",)
    search_fields = ("user__email", "client__name")
    autocomplete_fields = ("user", "client", "workspace")


@admin.register(UserProject)
class UserProjectAdmin(admin.ModelAdmin):
    list_display = ("user", "project", "workspace")
    list_filter = ("workspace",)
    search_fields = ("user__email", "project__name")
    autocomplete_fields = ("user", "project", "workspace")


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "workspace", "department", "date", "hours", "is_overtime", "client", "project", "task")
    list_filter = ("workspace", "department")
    date_hierarchy = "date"
    autocomplete_fields = ("user", "workspace", "department", "client", "project", "task")

    def save_model(self, request, obj, form, change):
        obj.save(skip_access_check=request.user.is_superuser)
