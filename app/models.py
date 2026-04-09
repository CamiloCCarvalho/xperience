from django.db import models
from django.contrib.auth.models import AbstractUser
from typing import ClassVar
from django.contrib.auth.models import BaseUserManager
from django.core.validators import MinValueValidator, MaxValueValidator


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    PATH_TO_USER_IMAGE = "app/images/users/%Y/%m/%d/"

    class PlatformRole(models.TextChoices):
        ADMIN = "admin", "Administrador da plataforma"
        MEMBER = "member", "Membro"

    username = None  # type: ignore
    email = models.EmailField(unique=True)

    platform_role = models.CharField(
        max_length=20,
        choices=PlatformRole.choices,
        default=PlatformRole.MEMBER,
    )

    is_verified = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    is_expired = models.BooleanField(default=False)
    is_inactive = models.BooleanField(default=False)

    avatar = models.ImageField(upload_to=PATH_TO_USER_IMAGE, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: ClassVar[CustomUserManager] = CustomUserManager() # type: ignore

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-created_at"]

    def __str__(self):
        return self.first_name + " - " + self.email


class Workspace(models.Model):
    """
    Workspace model
    """

    PATH_TO_WORKSPACE_IMAGE = "app/images/workspaces/%Y/%m/%d/"

    owner = models.ForeignKey('User', on_delete=models.CASCADE)
    workspace_name = models.CharField(max_length=255)
    workspace_description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    workspace_avatar = models.ImageField(
        upload_to=PATH_TO_WORKSPACE_IMAGE, 
        blank=True, 
        null=True
    )

    class Meta:
        verbose_name = "Workspace"
        verbose_name_plural = "Workspaces"
        ordering = ["-created_at"]

    def __str__(self):
        return self.workspace_name + " - " + self.owner.first_name + " " + self.owner.last_name


class Membership(models.Model):
    """
    Vínculo usuário ↔ workspace. Um mesmo usuário pode ter vários memberships
    (vários workspaces do mesmo gestor ou de gestores diferentes).
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")

    role = models.CharField(
        max_length=20,
        choices=[
            ("admin", "Admin"),
            ("manager", "Manager"),
            ("user", "User"),
        ],
        default="user"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "workspace")


class WorkSchedule(models.Model):
    """Regras de expediente por workspace."""

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="work_schedules",
    )
    name = models.CharField(max_length=255)
    working_days = models.JSONField(
        default=list,
        help_text='Lista de chaves: "mon","tue","wed","thu","fri","sat","sun"',
    )
    expected_hours_per_day = models.PositiveSmallIntegerField(
        default=8,
        validators=[MinValueValidator(1), MaxValueValidator(24)],
    )
    has_fixed_days = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Expediente"
        verbose_name_plural = "Expedientes"

    def __str__(self):
        return f"{self.name} ({self.workspace})"


class TimeEntryTemplate(models.Model):
    """
    Define quais blocos de campos aparecem nos apontamentos (flags fixas, sem JSON schema).
    """

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="time_entry_templates",
    )
    name = models.CharField(max_length=255)
    use_client = models.BooleanField(default=False)
    use_project = models.BooleanField(default=False)
    use_task = models.BooleanField(default=False)
    use_type = models.BooleanField(default=False)
    use_description = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Template de apontamento"
        verbose_name_plural = "Templates de apontamento"

    def __str__(self):
        return f"{self.name} ({self.workspace})"


class Department(models.Model):
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="departments",
    )
    name = models.CharField(max_length=255)
    schedule = models.ForeignKey(
        WorkSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="departments",
    )
    template = models.ForeignKey(
        TimeEntryTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="departments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        unique_together = ("workspace", "name")
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"

    def __str__(self):
        return f"{self.name} ({self.workspace})"


class UserDepartment(models.Model):
    """Um departamento por usuário em cada workspace."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_departments")
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="user_departments",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="user_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "workspace")
        verbose_name = "Departamento do usuário"
        verbose_name_plural = "Departamentos dos usuários"

    def __str__(self):
        return f"{self.user.email} → {self.department.name}"


class TimeEntry(models.Model):
    class EntryType(models.TextChoices):
        INTERNAL = "internal", "Interno"
        EXTERNAL = "external", "Externo"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="time_entries")
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="time_entries",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="time_entries",
    )
    date = models.DateField()
    hours = models.DecimalField(max_digits=6, decimal_places=2)
    client = models.CharField(max_length=255, blank=True)
    project = models.CharField(max_length=255, blank=True)
    task = models.CharField(max_length=255, blank=True)
    entry_type = models.CharField(
        max_length=20,
        choices=EntryType.choices,
        blank=True,
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-pk"]
        verbose_name = "Apontamento"
        verbose_name_plural = "Apontamentos"

    def __str__(self):
        return f"{self.user.email} {self.date} {self.hours}h"