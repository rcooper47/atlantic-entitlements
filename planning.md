# Atlantic Entitlements — Implementation Plan

## Context

Build a Django-based entitlements system for a publisher offering three hierarchical products (Digital ⊂ Print ⊂ Premium). The system must associate users with products and correctly answer **"what is this user entitled to right now"** under all lifecycle states: active, expired, or revoked.

The data model is intentionally simple: `Feature`, `Product`, `Entitlement`. Capabilities live as first-class `Feature` rows linked to `Product` via M2M, so the catalog is fully driven by data — no tier math, no derived flags. Expiration (time-based) and revocation (event-based) are distinct fields on `Entitlement` but resolve through a single "active at time T" predicate, supporting time-travel queries needed for deterministic tests and historical audits.

## Assumptions (flag any to change)

1. **API-only.** Django admin for inspection; no custom UI.
2. **Plain Django views** (no DRF). Class-based `django.views.View` subclasses for method dispatch; JSON via `json.loads(request.body)` and `JsonResponse`.
3. **SQLite** for development (single settings change to swap to Postgres).
4. **Multiple concurrent entitlements per user are allowed.** A user's effective access is the **union of features** across all currently-active entitlements.
5. **Django's built-in `auth.User`** — no custom user model.
6. **Revocation is permanent.** Once revoked, an entitlement stays revoked; re-grant to restore access.

## Domain Model

### `Feature`
| Field   | Type                       | Notes                     |
|---------|----------------------------|---------------------------|
| `name`  | `CharField(unique=True)`   | e.g. `web_access`, `print_magazine`, `ad_free` |

### `Product`
| Field      | Type                       | Notes                                            |
|------------|----------------------------|--------------------------------------------------|
| `name`     | `CharField(unique=True)`   | e.g. `Digital`, `Print`, `Premium`               |
| `features` | `M2M → Feature`            | Explicit capability set per product              |

Seeded via data migration (`0002_seed_catalog.py`):
- `web_access`, `print_magazine`, `ad_free` features.
- `Digital` → {`web_access`}.
- `Print` → {`web_access`, `print_magazine`}.
- `Premium` → {`web_access`, `print_magazine`, `ad_free`}.

### `Entitlement`
| Field         | Type                         | Notes                                                |
|---------------|------------------------------|------------------------------------------------------|
| `user`        | `FK → auth.User`             | `on_delete=CASCADE`                                  |
| `product`     | `FK → Product`               | `on_delete=PROTECT` (preserve history)               |
| `granted_at`  | `DateTimeField`              | default `now()`                                      |
| `expires_at`  | `DateTimeField(null=True)`   | `NULL` ⇒ open-ended                                  |
| `revoked_at`  | `DateTimeField(null=True)`   | Set on revoke; immutable afterward                   |

**Active-at-time predicate** (drives every "right now" query):
```
granted_at <= at
  AND (expires_at IS NULL OR expires_at > at)
  AND revoked_at IS NULL
```

Revocation is **immediate and absolute**: setting `revoked_at` makes the entitlement inactive at every `at` (including timestamps before the revoke). Only `expires_at` is compared against `at`. Implication: time-travel queries against revoked entitlements always return inactive — you cannot ask "was this active *before* revocation?" If that history matters later, we'd add an event log.

Index: `(user, revoked_at, expires_at)` for fast active-set lookups (most selective field first).

### Query helpers
On a custom `EntitlementQuerySet`:
- `active_for(user, at=None)` → queryset of currently-active entitlements (defaults `at=now`).
- `features_for(user, at=None)` → resolved set of feature names (union across active entitlements).

Both accept `at` so tests and historical queries use the same code path as live calls.

## API

Single app: `entitlements`.

| Method | Path                                            | Purpose                                          |
|--------|-------------------------------------------------|--------------------------------------------------|
| GET    | `/api/users/<id>/entitlements/`                 | Full history (all entitlements: active, expired, revoked) |
| GET    | `/api/users/<id>/entitlements/?active=true`     | Currently-active entitlements + resolved feature set |
| POST   | `/api/users/<id>/entitlements/`                 | Grant. Body: `{product_name, expires_at?}`       |
| DELETE | `/api/entitlements/<id>/`                       | Idempotent soft delete: sets `revoked_at=now()` if unset, otherwise no-op. Always returns `204 No Content`. Row is never hard-deleted. |

Notes on the active-filter:
- `?active=true` filters using the same active-at-time predicate as `Entitlement.objects.active_for(user)` and additionally returns the resolved feature set (union across active entitlements). Without `active=true`, the response is the raw history list with no feature resolution.
- `?active=false` (or absent) returns the full history. No other values are accepted.
- The single endpoint replaces both the old `/entitlements/grant/` and `/users/<id>/entitlement/` (singular) routes — grant is `POST` on the user's collection, and the effective-summary view is just the active-filtered `GET`.

Permissions: Django's built-in auth — `@method_decorator(login_required)` for reads, `@method_decorator(staff_member_required)` for writes (POST/DELETE). Adjustable for the demo.

CSRF: The write endpoints are JSON APIs intended for non-browser clients, so the view classes will use `@method_decorator(csrf_exempt)`. (If a browser-facing UI is added later, switch to CSRF tokens.)

Response shape:
- `GET /api/users/<id>/entitlements/` → `{"entitlements": [ {id, product_name, granted_at, expires_at, revoked_at}, ... ]}`
- `GET /api/users/<id>/entitlements/?active=true` → `{"entitlements": [...active only...], "features": ["web_access", ...]}`
- `POST /api/users/<id>/entitlements/` → `201` with the created entitlement object.
- `DELETE /api/entitlements/<id>/` → `204 No Content`, empty body.
- Errors → `JsonResponse({"error": "..."}, status=4xx)`. Validation handled inline in the view (no serializer layer).

## Project Layout

```
manage.py
requirements.txt
atlantic_entitlements/        # project package
  __init__.py
  settings.py
  urls.py
  wsgi.py
  asgi.py
entitlements/                 # app
  __init__.py
  apps.py
  admin.py
  models.py
  views.py
  urls.py
  migrations/
    0001_initial.py
    0002_seed_catalog.py
  tests/
    __init__.py
    test_models.py
    test_lifecycle.py
    test_api.py
README.md                     # overwrite stub with setup + usage
planning.md                   # this file
```

## Lifecycle Test Matrix (the heart of correctness)

| Scenario                                                                | Expected                                  |
|-------------------------------------------------------------------------|-------------------------------------------|
| Grant Digital, query now                                                | features = {`web_access`}                 |
| Grant Premium with `expires_at = now + 1d`, query at `now + 2d`         | features = ∅                              |
| Grant Premium then revoke, query immediately after                      | features = ∅                              |
| Grant Premium with future `expires_at`, revoke before expiry            | features = ∅ immediately and forever      |
| Revoke a grant, then query at a time **before** the revoke (time-travel)| features = ∅ (revocation is absolute, not time-bounded) |
| Grant Digital + Premium concurrently                                    | features = {`web_access`, `print_magazine`, `ad_free`} |
| Grant Premium, query at `granted_at - 1s` (time-travel)                 | features = ∅ (not yet started)            |
| DELETE an already-revoked entitlement                                   | idempotent: `revoked_at` unchanged, still `204` |
| User with no entitlements                                               | features = ∅                              |

Plus model tests (constraints, defaults) and API tests (auth, payloads).

## Verification

1. **Bootstrap**
   ```
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py createsuperuser
   ```

2. **Run tests** — must all pass:
   ```
   python manage.py test
   ```

3. **Smoke test the API**:
   - `POST /api/users/1/entitlements/` with `{"product_name":"Digital"}` → `GET /api/users/1/entitlements/?active=true` returns `{"features":["web_access"], ...}`.
   - `POST /api/users/1/entitlements/` with `{"product_name":"Premium","expires_at":"<now+1d>"}` → active features expand to all three.
   - `DELETE /api/entitlements/<premium_id>/` → active features fall back to `{"web_access"}`. Issue the same DELETE again → still `204`, `revoked_at` unchanged.
   - `GET /api/users/1/entitlements/` → full history shows both grants, one with `revoked_at` populated.

4. **Inspect via admin** — verify timestamps recorded as expected.

## Out of Scope

- Payment processing, billing cycles, auto-renewal.
- A custom frontend.
- Audit log beyond `granted_at` / `revoked_at`.
- Bulk grant / migration tooling.

## Key Files to Create

- `atlantic_entitlements/settings.py` — `entitlements` app installed (no DRF).
- `atlantic_entitlements/urls.py` — wires `entitlements.urls`.
- `entitlements/models.py` — `Feature`, `Product`, `Entitlement` (with `EntitlementQuerySet`).
- `entitlements/views.py` — class-based `View` subclasses: `UserEntitlementsView` (GET/POST) and `EntitlementDetailView` (DELETE). JSON in/out, inline validation.
- `entitlements/urls.py` — two URL patterns.
- `entitlements/migrations/0002_seed_catalog.py` — data migration seeding features, products, and the M2M links.
- `entitlements/tests/test_lifecycle.py` — the test matrix above.
- `README.md` — setup + API usage.
