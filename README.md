# atlantic-entitlements

A Django-based entitlements system for a publisher offering three hierarchical products (Digital ⊂ Print ⊂ Premium). It associates users with products and answers **"what is this user entitled to right now"** under all lifecycle states: active, expired, or revoked.

See `planning.md` for the full design rationale.

## Stack

- Django 4.2
- Plain Django class-based views (no DRF)
- SQLite (single settings change to swap to Postgres)

## Setup

```bash
python3 manage.py migrate
python3 manage.py createsuperuser   # for admin + staff-only write endpoints
python3 manage.py runserver
```

The three products and their features are seeded by the `0002_seed_catalog` data migration — no manual setup required.

## Models

| Model         | Fields                                                                 |
|---------------|------------------------------------------------------------------------|
| `Feature`     | `name` (unique)                                                        |
| `Product`     | `name` (unique), `features` (M2M → Feature)                            |
| `Entitlement` | `user`, `product`, `granted_at`, `expires_at?`, `revoked_at?`          |

Catalog (seeded):

| Product  | Features                                       |
|----------|------------------------------------------------|
| Digital  | `web_access`                                   |
| Print    | `web_access`, `print_magazine`                 |
| Premium  | `web_access`, `print_magazine`, `ad_free`      |

## Active-at-time predicate

An entitlement is **active at time `t`** iff:

```
granted_at <= t
  AND (expires_at IS NULL OR expires_at > t)
  AND revoked_at IS NULL
```

Revocation is **immediate and absolute**: once `revoked_at` is set, the entitlement is inactive at every `t` (including timestamps before the revoke). Only `expires_at` is time-compared. A user's effective feature set is the **union of features** across all currently-active entitlements.

## API

All endpoints are mounted under `/api/`.

| Method | Path                                            | Auth         | Purpose                                      |
|--------|-------------------------------------------------|--------------|----------------------------------------------|
| GET    | `/api/users/<id>/entitlements/`                 | authenticated| Full history (active + expired + revoked)    |
| GET    | `/api/users/<id>/entitlements/?active=true`     | authenticated| Active only + resolved feature set           |
| POST   | `/api/users/<id>/entitlements/`                 | staff        | Grant. Body: `{product_name, expires_at?}`   |
| DELETE | `/api/entitlements/<id>/`                       | staff        | Idempotent soft-delete: sets `revoked_at`    |

### Examples

Grant Digital to user 1:
```bash
curl -X POST http://localhost:8000/api/users/1/entitlements/ \
  -H "Content-Type: application/json" \
  -u admin:<password> \
  -d '{"product_name": "Digital"}'
```

Query current entitlements + features:
```bash
curl http://localhost:8000/api/users/1/entitlements/?active=true \
  -u admin:<password>
# {
#   "entitlements": [{"id": 1, "user_id": 1, "product_name": "Digital", ...}],
#   "features": ["web_access"]
# }
```

Revoke (idempotent — second call is a no-op, `revoked_at` is not refreshed):
```bash
curl -X DELETE http://localhost:8000/api/entitlements/1/ \
  -u admin:<password>
```

## Programmatic access

```python
from entitlements.models import Entitlement

# All currently-active entitlements for a user
Entitlement.objects.active_for(user)

# Resolved feature set (union across active entitlements)
Entitlement.objects.features_for(user)

# Historical: "what did this user have on 2025-12-15?"
Entitlement.objects.features_for(user, at=some_datetime)
```

## Tests

```bash
python3 manage.py test entitlements
```

34 tests covering the lifecycle matrix (active, expired, revoked, time-travel, overlapping grants, idempotent revocation), model defaults, catalog seeding, and API behavior (auth, validation, status codes).
