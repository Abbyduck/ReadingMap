"""Create a local-development administrator without hardcoding a password."""
import secrets
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from accounts.models import User

class Command(BaseCommand):
    help = "Create one local development admin; never resets an existing account."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="admin@readingmap.local")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Only for local development. Use createsuperuser in production.")
        email = options["email"].strip().lower()
        if User.objects.filter(is_superuser=True).exists() or User.objects.filter(email=email).exists():
            self.stdout.write("An administrator/account already exists; no account or password changed.")
            return
        password = secrets.token_urlsafe(24)
        target = settings.BASE_DIR / ".local" / "admin-credentials.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise CommandError("Credential file exists; refusing to overwrite.")
        User.objects.create_superuser(email, password, name="管理员")
        target.write_text(f"Local development only. Change this password before deployment.\nURL: http://127.0.0.1:8010/django-admin/\nEmail: {email}\nPassword: {password}\n", encoding="utf-8")
        self.stdout.write(f"Created local administrator. Credentials: {target}")
