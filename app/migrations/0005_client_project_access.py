# Generated manually for Client / Project / Task / access links and TimeEntry FKs

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0004_time_tracking_config"),
    ]

    operations = [
        migrations.CreateModel(
            name="Client",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("document", models.CharField(blank=True, max_length=64)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=64)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_clients",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="clients",
                        to="app.workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Cliente",
                "verbose_name_plural": "Clientes",
                "ordering": ["name", "pk"],
            },
        ),
        migrations.CreateModel(
            name="Project",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="projects",
                        to="app.client",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_projects",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="projects",
                        to="app.workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Projeto",
                "verbose_name_plural": "Projetos",
                "ordering": ["name", "pk"],
            },
        ),
        migrations.CreateModel(
            name="Task",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tasks",
                        to="app.project",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tarefa",
                "verbose_name_plural": "Tarefas",
                "ordering": ["name", "pk"],
            },
        ),
        migrations.CreateModel(
            name="UserClient",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_access_links",
                        to="app.client",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="client_access_links",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_client_links",
                        to="app.workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Acesso usuário → cliente",
                "verbose_name_plural": "Acessos usuário → cliente",
            },
        ),
        migrations.AddConstraint(
            model_name="userclient",
            constraint=models.UniqueConstraint(
                fields=("user", "client", "workspace"),
                name="app_userclient_user_client_workspace_uniq",
            ),
        ),
        migrations.CreateModel(
            name="UserProject",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_access_links",
                        to="app.project",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="project_access_links",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_project_links",
                        to="app.workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Acesso usuário → projeto",
                "verbose_name_plural": "Acessos usuário → projeto",
            },
        ),
        migrations.AddConstraint(
            model_name="userproject",
            constraint=models.UniqueConstraint(
                fields=("user", "project", "workspace"),
                name="app_userproject_user_project_workspace_uniq",
            ),
        ),
        migrations.RemoveField(
            model_name="timeentry",
            name="client",
        ),
        migrations.RemoveField(
            model_name="timeentry",
            name="project",
        ),
        migrations.RemoveField(
            model_name="timeentry",
            name="task",
        ),
        migrations.AddField(
            model_name="timeentry",
            name="client",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="time_entries",
                to="app.client",
            ),
        ),
        migrations.AddField(
            model_name="timeentry",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="time_entries",
                to="app.project",
            ),
        ),
        migrations.AddField(
            model_name="timeentry",
            name="task",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="time_entries",
                to="app.task",
            ),
        ),
    ]
