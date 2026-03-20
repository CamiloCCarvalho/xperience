from django.db import models
from django.contrib.auth.models import AbstractUser, PermissionsMixin, UserManager




class CustomUserManager(UserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")

        email = self.normalize_email(email)
        extra_fields.setdefault("username", email)
        return super().create_user(email=email, password=password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(email, password, **extra_fields)

# Create your models here.
class User(AbstractUser, PermissionsMixin):
    """
    User model
    """
    PATH_TO_USER_IMAGE = "app/images/users/%Y/%m/%d/"

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    is_expired = models.BooleanField(default=False)
    is_inactive = models.BooleanField(default=False)
    
    avatar = models.ImageField(
        upload_to=PATH_TO_USER_IMAGE, 
        blank=True, 
        null=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    #objects: CustomUserManager = CustomUserManager()

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
