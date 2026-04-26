# Generated manually for Mural status options + palette keys on columns/cards.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0021_workspace_mural_members_lane_lock"),
    ]

    operations = [
        migrations.CreateModel(
            name="MuralStatusOption",
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
                ("name", models.CharField(max_length=120)),
                ("position", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "color_key",
                    models.CharField(
                        help_text="Chave da paleta fixa do mural (ex.: blue, green).",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="mural_status_options_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="mural_status_options_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mural_status_options",
                        to="app.workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Status do mural",
                "verbose_name_plural": "Status do mural",
                "ordering": ["workspace", "position", "pk"],
            },
        ),
        migrations.AddIndex(
            model_name="muralstatusoption",
            index=models.Index(fields=["workspace", "position"], name="app_muralstat_ws_pos_idx"),
        ),
        migrations.AddIndex(
            model_name="muralstatusoption",
            index=models.Index(
                fields=["workspace", "is_active", "position"],
                name="app_muralstat_ws_act_pos_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="muralstatusoption",
            constraint=models.UniqueConstraint(
                fields=("workspace", "name"),
                name="app_muralstatusoption_workspace_name_uniq",
            ),
        ),
        migrations.AddField(
            model_name="privateboardcolumn",
            name="color_key",
            field=models.CharField(
                blank=True,
                help_text="Chave opcional da paleta fixa para realce da coluna.",
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="boardcard",
            name="color_key",
            field=models.CharField(
                blank=True,
                help_text="Chave opcional da paleta fixa para realce do card.",
                max_length=16,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="boardcard",
            name="mural_status",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="board_cards",
                to="app.muralstatusoption",
            ),
        ),
    ]
