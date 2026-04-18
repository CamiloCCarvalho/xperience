from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser
from typing import ClassVar
from django.contrib.auth.models import BaseUserManager
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


def _check_constraint(*, predicate, name: str) -> models.CheckConstraint:
    """
    Compatibilidade entre versões de Django:
    - antigas: CheckConstraint(check=...)
    - novas:   CheckConstraint(condition=...)
    """
    try:
        return models.CheckConstraint(condition=predicate, name=name)
    except TypeError:
        return models.CheckConstraint(check=predicate, name=name)


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
    birth_date = models.DateField(
        null=True,
        blank=True,
        help_text="Data de nascimento global da pessoa (não depende de workspace).",
    )
    platform_join_date = models.DateField(
        default=timezone.localdate,
        help_text="Data de entrada na plataforma (diferente de created_at técnico).",
    )

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

    @property
    def age(self):
        """Idade calculada em tempo real a partir de birth_date (não persistida)."""
        if not self.birth_date:
            return None
        today = timezone.localdate()
        years = today.year - self.birth_date.year
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years


class Workspace(models.Model):
    """
    Workspace model
    """

    PATH_TO_WORKSPACE_IMAGE = "app/images/workspaces/%Y/%m/%d/"

    owner = models.ForeignKey('User', on_delete=models.CASCADE)
    workspace_name = models.CharField(max_length=255)
    workspace_description = models.TextField(blank=True)
    budget_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_workspaces",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_workspaces",
    )
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


class EmployeeProfile(models.Model):
    """Vínculo empregatício atual de um usuário em um workspace."""

    class EmploymentStatus(models.TextChoices):
        ACTIVE = "active", "Ativo"
        ON_LEAVE = "on_leave", "Afastado"
        TERMINATED = "terminated", "Desligado"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="employee_profiles",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="employee_profiles",
    )
    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
    )
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    current_job_title = models.CharField(
        max_length=255,
        blank=True,
        help_text="Cargo atual para leitura rápida sem depender apenas de histórico.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "workspace"),
                name="app_employeeprofile_user_workspace_uniq",
            ),
            _check_constraint(
                predicate=Q(termination_date__isnull=True) | Q(termination_date__gte=models.F("hire_date")),
                name="app_employeeprofile_termination_after_hire",
            ),
        ]
        verbose_name = "Vínculo do colaborador"
        verbose_name_plural = "Vínculos dos colaboradores"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.termination_date and self.termination_date < self.hire_date:
            errors["termination_date"] = "A data de desligamento não pode ser menor que a data de admissão."
        if self.employment_status == self.EmploymentStatus.TERMINATED and not self.termination_date:
            errors["termination_date"] = "Informe a data de desligamento para status desligado."
        if self.termination_date and self.employment_status != self.EmploymentStatus.TERMINATED:
            errors["employment_status"] = "Use status desligado quando houver data de desligamento."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} @ {self.workspace.workspace_name}"


class JobHistory(models.Model):
    """Histórico de cargos de um vínculo (separado da remuneração)."""

    employee_profile = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="job_history_entries",
    )
    job_title = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=("employee_profile",),
                condition=Q(end_date__isnull=True),
                name="app_jobhistory_single_current_job_per_profile",
            ),
            _check_constraint(
                predicate=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="app_jobhistory_end_after_start",
            ),
        ]
        verbose_name = "Histórico de cargo"
        verbose_name_plural = "Históricos de cargo"

    def clean(self) -> None:
        super().clean()
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "A data final não pode ser anterior à data inicial."})

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee_profile.user.email} - {self.job_title}"


class CompensationHistory(models.Model):
    """Histórico de remuneração mensal/horista por vínculo."""

    class CompensationType(models.TextChoices):
        MONTHLY = "monthly", "Mensal"
        HOURLY = "hourly", "Por hora"

    employee_profile = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.CASCADE,
        related_name="compensation_history_entries",
    )
    compensation_type = models.CharField(max_length=20, choices=CompensationType.choices)
    monthly_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=("employee_profile",),
                condition=Q(end_date__isnull=True),
                name="app_compensationhistory_single_current_compensation_per_profile",
            ),
            _check_constraint(
                predicate=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="app_compensationhistory_end_after_start",
            ),
            _check_constraint(
                predicate=(
                    (Q(compensation_type="monthly") & Q(monthly_salary__isnull=False) & Q(hourly_rate__isnull=True))
                    | (Q(compensation_type="hourly") & Q(hourly_rate__isnull=False) & Q(monthly_salary__isnull=True))
                ),
                name="app_compensationhistory_fields_by_type",
            ),
        ]
        verbose_name = "Histórico de remuneração"
        verbose_name_plural = "Históricos de remuneração"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "A data final não pode ser anterior à data inicial."
        if self.compensation_type == self.CompensationType.MONTHLY:
            if self.monthly_salary is None:
                errors["monthly_salary"] = "Informe o salário mensal para remuneração mensal."
            if self.hourly_rate is not None:
                errors["hourly_rate"] = "Não informe valor por hora para remuneração mensal."
        elif self.compensation_type == self.CompensationType.HOURLY:
            if self.hourly_rate is None:
                errors["hourly_rate"] = "Informe o valor por hora para remuneração por hora."
            if self.monthly_salary is not None:
                errors["monthly_salary"] = "Não informe salário mensal para remuneração por hora."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee_profile.user.email} - {self.get_compensation_type_display()}"


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
    has_fixed_days = models.BooleanField(
        default=True,
        verbose_name="Folga Fixa",
        help_text="Se ativado, o expediente usa os dias da semana escolhidos de forma fixa.",
    )
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
    class TimeTrackingMode(models.TextChoices):
        DURATION = "duration", "Duração"
        TIME_RANGE = "time_range", "Intervalo"
        TIMER = "timer", "Cronômetro"

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
    time_tracking_mode = models.CharField(
        max_length=20,
        choices=TimeTrackingMode.choices,
        default=TimeTrackingMode.DURATION,
    )
    can_edit_time_entries = models.BooleanField(
        default=True,
        help_text="Se falso, membros não devem editar apontamentos salvos (regra de aplicação na view).",
    )
    can_delete_time_entries = models.BooleanField(
        default=True,
        help_text="Se falso, membros não devem excluir apontamentos (regra de aplicação na view).",
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
    """Permite histórico de realocação e departamento principal por workspace."""

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
    is_primary = models.BooleanField(default=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Garante um único departamento principal por usuário/workspace.
            models.UniqueConstraint(
                fields=("user", "workspace"),
                condition=Q(is_primary=True),
                name="app_userdepartment_primary_per_workspace",
            ),
            # Histórico: só pode existir um vínculo "ativo" (sem end_date) por usuário/workspace.
            models.UniqueConstraint(
                fields=("user", "workspace"),
                condition=Q(end_date__isnull=True),
                name="app_userdepartment_single_active_per_workspace",
            ),
        ]
        verbose_name = "Departamento do usuário"
        verbose_name_plural = "Departamentos dos usuários"

    def clean(self) -> None:
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                {"end_date": "A data final não pode ser anterior à data inicial."}
            )

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
    budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_clients",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_clients",
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
    budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    deadline = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_projects",
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


class TimeEntryQuerySet(models.QuerySet):
    """Consultas de apontamentos; use ``saved_only()`` em agregações (rascunhos ficam de fora)."""

    def saved_only(self):
        return self.filter(status=self.model.Status.SAVED)


class TimeEntry(models.Model):
    class EntryType(models.TextChoices):
        INTERNAL = "internal", "Interno"
        EXTERNAL = "external", "Externo"

    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        SAVED = "saved", "Salvo"

    class EntryMode(models.TextChoices):
        DURATION = "duration", "Duração"
        TIME_RANGE = "time_range", "Intervalo"
        TIMER = "timer", "Cronômetro"

    _MAX_MINUTES_PER_DAY = 24 * 60

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
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SAVED,
    )
    entry_mode = models.CharField(
        max_length=20,
        choices=EntryMode.choices,
        default=EntryMode.DURATION,
    )
    timer_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Início do cronômetro (rascunho em andamento ou referência ao salvar).",
    )
    date = models.DateField()
    hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
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
    is_overtime = models.BooleanField(
        default=False,
        help_text="Indica se o apontamento é hora extra (opcional no lançamento).",
    )
    timer_pending_template_completion = models.BooleanField(
        default=False,
        help_text=(
            "Após parar o cronômetro: indica que o registro salvo ainda aguarda "
            "'Salvar dados do apontamento' ou descarte explícito."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TimeEntryQuerySet.as_manager()

    class Meta:
        ordering = ["-date", "-pk"]
        indexes = [
            models.Index(fields=["workspace", "date"]),
            models.Index(fields=["user", "date"]),
            models.Index(fields=["project"]),
            models.Index(fields=["user", "workspace", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("user", "workspace"),
                condition=Q(status="draft"),
                name="app_timeentry_one_draft_per_user_workspace",
            ),
        ]
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

        if self.department_id and self.workspace_id and self.department.workspace_id != self.workspace_id:
            errors["department"] = "O departamento não pertence a este workspace."

        is_draft = self.status == self.Status.DRAFT
        has_hours = self.hours is not None
        has_start = self.start_time is not None
        has_end = self.end_time is not None
        has_time_range = has_start and has_end

        if not is_draft and has_start != has_end:
            errors["end_time"] = "Informe início e fim para usar o modo por intervalo."

        if (
            not is_draft
            and has_time_range
            and self.entry_mode in (self.EntryMode.TIME_RANGE, self.EntryMode.TIMER)
        ):
            if self.end_time <= self.start_time:
                errors["end_time"] = (
                    "O horário de fim deve ser maior que o de início no mesmo dia "
                    "(apontamento não pode atravessar meia-noite)."
                )
            else:
                start_total_minutes = self.start_time.hour * 60 + self.start_time.minute
                end_total_minutes = self.end_time.hour * 60 + self.end_time.minute
                self.duration_minutes = end_total_minutes - start_total_minutes

        if has_hours and self.duration_minutes is None:
            minutes_decimal = (self.hours * Decimal("60")).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
            self.duration_minutes = int(minutes_decimal)

        if is_draft:
            if errors:
                raise ValidationError(errors)
            return

        # --- salvo: validação por modo de entrada ---
        mode = self.entry_mode
        if mode == self.EntryMode.DURATION:
            if not has_hours and not (self.duration_minutes is not None and self.duration_minutes > 0):
                errors["hours"] = "Informe horas ou duração em minutos."
        elif mode == self.EntryMode.TIME_RANGE:
            if not has_time_range:
                errors["start_time"] = "Informe início e fim no mesmo dia."
        elif mode == self.EntryMode.TIMER:
            measurable = (
                has_hours
                or (self.duration_minutes is not None and self.duration_minutes > 0)
                or has_time_range
            )
            if not measurable:
                errors["hours"] = "Finalize o cronômetro com duração ou intervalo de horários."
            if self.timer_started_at and self.timer_started_at.date() != self.date:
                errors["date"] = "A data do apontamento deve ser a mesma do início do cronômetro."
        else:
            errors["entry_mode"] = "Modo de entrada inválido."

        if self.duration_minutes is not None and self.duration_minutes > self._MAX_MINUTES_PER_DAY:
            errors["duration_minutes"] = "Duração não pode exceder 24 horas no mesmo dia (MVP)."

        if has_hours and self.hours is not None and self.hours > Decimal("24"):
            errors["hours"] = "Horas não podem exceder 24 por apontamento (MVP)."

        if errors:
            raise ValidationError(errors)

    def _assert_user_access(self) -> None:
        """Garante que o usuário do apontamento tem vínculos UserClient / UserProject."""
        if self.status == self.Status.DRAFT and not self.client_id and not self.project_id:
            return
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
        if self.hours is not None:
            return f"{self.user.email} {self.date} {self.hours}h"
        return f"{self.user.email} {self.date} {self.duration_minutes}min"