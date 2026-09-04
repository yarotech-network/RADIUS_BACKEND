from django.core.management.base import BaseCommand
from django.db import transaction

from apps.routers.models import NASDevice
from apps.routers.secret_store import secret_store


class Command(BaseCommand):
    help = "Encrypt legacy plaintext router credentials (dry-run unless --apply is used)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist encryption. Without this flag, only report the number of rows.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        routers = NASDevice.objects.select_for_update().filter(
            nas_secret__isnull=False
        )
        changed = 0
        for router in routers.iterator():
            update_fields = []
            if router.nas_secret and not router.nas_secret.startswith("enc:v1:"):
                update_fields.append("nas_secret")
            if (
                router.routeros_password_encrypted
                and not router.routeros_password_encrypted.startswith("enc:v1:")
            ):
                update_fields.append("routeros_password_encrypted")
            if not update_fields:
                continue
            changed += 1
            if options["apply"]:
                if "nas_secret" in update_fields:
                    router.nas_secret = secret_store.encrypt(router.nas_secret)
                if "routeros_password_encrypted" in update_fields:
                    router.routeros_password_encrypted = secret_store.encrypt(
                        router.routeros_password_encrypted
                    )
                router.save(update_fields=update_fields)

        mode = "Encrypted" if options["apply"] else "Would encrypt"
        self.stdout.write(f"{mode} credentials for {changed} router(s).")
