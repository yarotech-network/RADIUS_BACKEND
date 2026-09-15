import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from apps.core.legacy_import import read_archive, draft_plan, coverage, execute_import, digest, ImportBlocked


class Command(BaseCommand):
    help = 'Inspect coverage, rehearse or apply an explicit reviewed replacement plan to staging.'

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True)
        parser.add_argument('--plan')
        parser.add_argument('--draft')
        parser.add_argument('--rehearse', action='store_true')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--reviewed-plan-sha256')
        parser.add_argument('--source-key-file')

    def handle(self, *args, **options):
        try:
            if options['apply'] and options['rehearse']:
                raise ImportBlocked('Choose either --apply or --rehearse, never both.')
            archive, source_digest = read_archive(Path(options['source']))
            if options['draft']:
                import os
                fd = os.open(options['draft'], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as output:
                    json.dump(draft_plan(archive, source_digest), output, indent=2)
                self.stdout.write('Draft created. It contains no automatic business mappings; complete and review it before rehearsal.')
                return
            if not options['plan']:
                raise ImportBlocked('Provide --plan or --draft.')
            plan = json.loads(Path(options['plan']).read_text(encoding='utf-8'))
            if options['apply'] and options['reviewed_plan_sha256'] != digest(plan):
                raise ImportBlocked('The exact reviewed plan SHA256 is required for apply.')
            if options['rehearse'] or options['apply']:
                cipher = None
                if options['source_key_file']:
                    from cryptography.fernet import Fernet
                    cipher = Fernet(Path(options['source_key_file']).read_bytes().strip())
                result = execute_import(archive, plan, source_digest, apply=options['apply'], source_cipher=cipher)
            else:
                result = coverage(archive, plan, source_digest)
            self.stdout.write(json.dumps(result, sort_keys=True))
        except ImportBlocked as exc:
            raise CommandError(str(exc))
        except Exception as exc:
            # Validation, SQL and crypto exceptions can contain source values.
            raise CommandError('Transfer failed ('+type(exc).__name__+'). Inspect the protected source and plan; no source values are logged.')
