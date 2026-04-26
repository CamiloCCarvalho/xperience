from django.db import migrations, models


def _backfill_financialentry_approval(apps, schema_editor):
    FinancialEntry = apps.get_model("app", "FinancialEntry")
    for entry in FinancialEntry.objects.filter(flow_type="outflow").iterator():
        entry.approval_status = "approved"
        entry.approved_at = entry.updated_at
        entry.approved_by_id = entry.updated_by_id or entry.created_by_id
        entry.save(
            update_fields=[
                "approval_status",
                "approved_at",
                "approved_by",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0018_jobrole_refactor"),
    ]

    operations = [
        migrations.AddField(
            model_name="financialentry",
            name="approval_status",
            field=models.CharField(
                choices=[
                    ("not_required", "Não requer aprovação"),
                    ("pending", "Pendente"),
                    ("processing", "Processando"),
                    ("approved", "Aprovado"),
                    ("rejected", "Reprovado"),
                ],
                default="not_required",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="financialentry",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="financialentry",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="approved_financial_entries",
                to="app.user",
            ),
        ),
        migrations.AddField(
            model_name="financialentry",
            name="decision_note",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="financialentry",
            name="rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="financialentry",
            name="rejected_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="rejected_financial_entries",
                to="app.user",
            ),
        ),
        migrations.RunPython(_backfill_financialentry_approval, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="financialentry",
            index=models.Index(fields=["workspace", "approval_status"], name="app_financi_workspa_b0553d_idx"),
        ),
    ]
