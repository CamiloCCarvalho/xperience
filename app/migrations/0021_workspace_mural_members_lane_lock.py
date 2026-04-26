from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0020_boardcard_public_lane_split"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspace",
            name="mural_members_lane_locked",
            field=models.BooleanField(default=False),
        ),
    ]
