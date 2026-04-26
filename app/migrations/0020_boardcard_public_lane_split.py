from django.db import migrations, models


def _compat_check_constraint(*, predicate, name: str):
    try:
        return models.CheckConstraint(condition=predicate, name=name)
    except TypeError:
        return models.CheckConstraint(check=predicate, name=name)


def _backfill_public_lane(apps, schema_editor):
    BoardCard = apps.get_model("app", "BoardCard")
    BoardCard.objects.filter(visibility="public", public_lane__isnull=True).update(public_lane="members")


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0019_financialentry_approval_flow"),
    ]

    operations = [
        migrations.AddField(
            model_name="boardcard",
            name="public_lane",
            field=models.CharField(
                blank=True,
                choices=[("members", "Membros"), ("management", "Gestão")],
                max_length=20,
                null=True,
            ),
        ),
        migrations.RunPython(_backfill_public_lane, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="boardcard",
            name="app_boardcard_public_workspace_position_uniq",
        ),
        migrations.AddConstraint(
            model_name="boardcard",
            constraint=_compat_check_constraint(
                predicate=(
                    models.Q(visibility="private", public_lane__isnull=True)
                    | models.Q(visibility="public", public_lane__isnull=False)
                ),
                name="app_boardcard_visibility_public_lane_consistency",
            ),
        ),
        migrations.AddConstraint(
            model_name="boardcard",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    visibility="public",
                    private_column__isnull=True,
                    public_lane__isnull=False,
                ),
                fields=("workspace", "public_lane", "position"),
                name="app_boardcard_public_lane_workspace_position_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="boardcard",
            index=models.Index(
                fields=["workspace", "visibility", "public_lane", "position"],
                name="app_boardca_ws_vis_lane_pos_idx",
            ),
        ),
    ]
