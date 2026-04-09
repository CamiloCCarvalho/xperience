from django.db.models.signals import post_save
from django.dispatch import receiver

from app.models import TimeEntryTemplate, Workspace


@receiver(post_save, sender=Workspace)
def create_default_time_entry_templates(
    sender,
    instance: Workspace,
    created: bool,
    **kwargs,
):
    if not created:
        return
    if TimeEntryTemplate.objects.filter(workspace=instance).exists():
        return
    TimeEntryTemplate.objects.bulk_create(
        [
            TimeEntryTemplate(
                workspace=instance,
                name="Simple",
                use_client=False,
                use_project=False,
                use_task=False,
                use_type=False,
                use_description=False,
            ),
            TimeEntryTemplate(
                workspace=instance,
                name="Operational",
                use_client=True,
                use_project=True,
                use_task=True,
                use_type=False,
                use_description=False,
            ),
            TimeEntryTemplate(
                workspace=instance,
                name="Professional",
                use_client=True,
                use_project=True,
                use_task=True,
                use_type=True,
                use_description=True,
            ),
        ]
    )
