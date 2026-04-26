from django.db import models
from django.contrib.auth.models import AbstractUser
from typing import ClassVar
from django.contrib.auth.models import BaseUserManager
from django.core.exceptions import PermissionDenied, ValidationError
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

    # Payment/card fields (stored minimally). Card numbers are NOT stored in plain text.
    card_hash = models.CharField(max_length=128, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    card_brand = models.CharField(max_length=50, blank=True)
    card_holder_name = models.CharField(max_length=255, blank=True)
    card_expiry_month = models.PositiveSmallIntegerField(null=True, blank=True)
    card_expiry_year = models.PositiveSmallIntegerField(null=True, blank=True)

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


class Client(models.Model):
    """Cliente do workspace (multi-tenant)."""

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="clients",
    )
    name = models.CharField(max_length=255)
    document = models.CharField(max_length=64, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_clients",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"

    def __str__(self):
        return f"{self.name} ({self.workspace})"


class Project(models.Model):
    """Projeto vinculado a um cliente do mesmo workspace."""

    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Projeto"
        verbose_name_plural = "Projetos"

    def clean(self) -> None:
        super().clean()
        if self.client_id and self.workspace_id and self.client.workspace_id != self.workspace_id:
            raise ValidationError(
                {"client": "O cliente deve pertencer ao mesmo workspace do projeto."}
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.client})"


class Task(models.Model):
    """Tarefa opcional dentro de um projeto."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Tarefa"
        verbose_name_plural = "Tarefas"

    def __str__(self):
        return f"{self.name} ({self.project})"


class UserClient(models.Model):
    """Define quais usuários podem usar qual cliente em um workspace."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="client_access_links",
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="user_access_links",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="user_client_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "client", "workspace"),
                name="app_userclient_user_client_workspace_uniq",
            ),
        ]
        verbose_name = "Acesso usuário → cliente"
        verbose_name_plural = "Acessos usuário → cliente"

    def clean(self) -> None:
        super().clean()
        if self.client_id and self.workspace_id and self.client.workspace_id != self.workspace_id:
            raise ValidationError(
                {"client": "O cliente deve pertencer ao workspace informado."}
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} → {self.client.name}"


class UserProject(models.Model):
    """Define quais usuários podem usar qual projeto em um workspace."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="project_access_links",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="user_access_links",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="user_project_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "project", "workspace"),
                name="app_userproject_user_project_workspace_uniq",
            ),
        ]
        verbose_name = "Acesso usuário → projeto"
        verbose_name_plural = "Acessos usuário → projeto"

    def clean(self) -> None:
        super().clean()
        if self.project_id and self.workspace_id and self.project.workspace_id != self.workspace_id:
            raise ValidationError(
                {"project": "O projeto deve pertencer ao workspace informado."}
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} → {self.project.name}"


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
    client = models.ForeignKey(
        Client,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="time_entries",
    )
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="time_entries",
    )
    task = models.ForeignKey(
        Task,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="time_entries",
    )
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

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.client_id and self.workspace_id and self.client.workspace_id != self.workspace_id:
            errors["client"] = "O cliente não pertence a este workspace."

        if self.project_id and self.workspace_id and self.project.workspace_id != self.workspace_id:
            errors["project"] = "O projeto não pertence a este workspace."

        if self.client_id and self.project_id and self.project.client_id != self.client_id:
            errors["project"] = "O projeto não pertence ao cliente selecionado."

        if self.task_id:
            if not self.project_id:
                errors["task"] = "Defina o projeto para associar uma tarefa."
            elif self.task.project_id != self.project_id:
                errors["task"] = "A tarefa não pertence ao projeto selecionado."

        if errors:
            raise ValidationError(errors)

    def _assert_user_access(self) -> None:
        """Garante que o usuário do apontamento tem vínculos UserClient / UserProject."""
        ws_id = self.workspace_id
        if self.client_id:
            has_client = UserClient.objects.filter(
                user_id=self.user_id,
                client_id=self.client_id,
                workspace_id=ws_id,
            ).exists()
            if not has_client:
                raise PermissionDenied("Usuário sem permissão para este cliente neste workspace.")
        if self.project_id:
            has_project = UserProject.objects.filter(
                user_id=self.user_id,
                project_id=self.project_id,
                workspace_id=ws_id,
            ).exists()
            if not has_project:
                raise PermissionDenied("Usuário sem permissão para este projeto neste workspace.")

    def save(self, *args, skip_access_check: bool = False, **kwargs) -> None:
        self.full_clean()
        if not skip_access_check:
            self._assert_user_access()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} {self.date} {self.hours}h"


class PaymentMethod(models.Model):
    """
    Método de pagamento associado a um usuário.

    Não armazena CVV nem o número completo do cartão em texto plano.
    Guarda um token (placeholder, NÃO substitui tokenização PCI),
    os últimos 4 dígitos e metadados auxiliares (validade, titular,
    plano contratado e CPF mascarado).
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="payment_methods",
    )
    token = models.CharField(max_length=128)
    holder_name = models.CharField(max_length=255, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    expiry_month = models.PositiveSmallIntegerField(null=True, blank=True)
    expiry_year = models.PositiveSmallIntegerField(null=True, blank=True)
    cpf_masked = models.CharField(max_length=32, blank=True)
    plan = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Método de pagamento"
        verbose_name_plural = "Métodos de pagamento"

    def __str__(self):
        last4 = self.card_last4 or "----"
        return f"{self.user.email} ****{last4}"