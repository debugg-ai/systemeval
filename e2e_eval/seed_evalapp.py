"""
Seed the eval-app INFRA (one-time): project + environment + admin credential.

NOT scenarios. Scenario tests are defined once in systemeval/e2e_eval/suites/*.json
(the single source of truth — id + goal + oracle + expect) and run_eval
resolve-or-creates each E2eTest from the suite's own goal. This script only
establishes what the API can't easily do: the eval-app project wired to a
token-visible team, plus an ExternalEnvironment + an ENCRYPTED admin credential so
the auth subworkflow can log into eval-app.

Run once inside the sentinal Django container:
    docker exec -i sentinal_django python manage.py shell < e2e_eval/seed_evalapp.py
"""
from backend.projects.models import (
    ExternalEnvironment,
    ExternalEnvironmentCredential,
    Project,
)

EVAL_URL = "http://host.docker.internal:8080"  # eval-app from browser-mgr Chrome
ADMIN_USER, ADMIN_PASS = "admin", "secret123"

# Reuse the team that makes local fixtures visible to the smoke token.
team = Project.objects.get(name="test-nextjs-flows").team

proj, created = Project.objects.get_or_create(
    name="eval-app", team=team,
    defaults={"description": "TaskFlow eval fixture (sentinal eval-app, :8080)"},
)
print(f"PROJECT eval-app id={proj.id} uuid={proj.uuid} created={created}")

env, _ = ExternalEnvironment.objects.get_or_create(
    project=proj, name="eval-app-local",
    defaults={"url": EVAL_URL, "username": ADMIN_USER, "is_default": True, "is_active": True},
)
env.url, env.username, env.is_default, env.is_active = EVAL_URL, ADMIN_USER, True, True
env.set_password(ADMIN_PASS)
env.save()

cred, _ = ExternalEnvironmentCredential.objects.get_or_create(
    environment=env, username=ADMIN_USER,
    defaults={"is_default": True, "label": "eval-app admin"},
)
cred.is_default = True
cred.set_password(ADMIN_PASS)
cred.save()
print(f"ENV id={env.id} url={env.url} | CRED id={cred.id} user={cred.username}")
print("Infra seeded. Scenario tests are auto-created by run_eval from suites/*.json.")
