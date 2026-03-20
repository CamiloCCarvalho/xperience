from django.contrib import admin
from .models import User
from .models import Workspace
# Register your models here.

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    ...

@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    ...
