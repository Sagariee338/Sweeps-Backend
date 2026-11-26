# Files lost in the upload

This repo was uploaded through GitHub's "Add files via upload" page, which drops
folders. Files with the same name in different apps (models.py, urls.py,
views.py, serializers.py, services.py, migrations) overwrote each other, so only
one copy of each survived. The surviving files have been moved back into their
apps on this branch, and empty `__init__.py` package markers have been added.

The backend will not start until the files below are restored from the
original project on your computer (the folder that has `backend/` and
`frontend/` side by side).

## Whole apps missing (only settings mention them)

- `wallet/` — models, services (balanced ledger), views, urls, migrations
- `provider_accounts/` — models, services, views, urls, admin, free_credits, migrations
- `ops/` — views, urls
- `support/` — models, views, urls, migrations

## Missing pieces of apps that partly survived

- `config/urls.py` (root URL config)
- `identity/apps.py`, `identity/views/notifications.py`
- `catalog/apps.py`, `catalog/models.py`, `catalog/serializers.py`, `catalog/urls.py`, `catalog/migrations/`
- `demo/apps.py`, `demo/models.py`, `demo/serializers.py`, `demo/urls.py`, `demo/migrations/0001_initial.py`
- `demo/services/games.py`, `payments.py`, `redemptions.py`, `wallets.py`
- `integrations/__init__.py`, `integrations/models/` (game.py, payment.py, development_payments.py), `integrations/urls.py`, `integrations/migrations/`, `integrations/management/commands/sync_firekirin_catalog.py`, `integrations/tests/`
- `integrations/game_clients/common/` (credentials, errors, validation)
- `integrations/game_clients/{firekirin,orion,fastapi,gamevault,juwa2,gameroom}/` vendor clients, including `juwa2/mock.py`
- `.env.example`

`integrations/admin.py` is the empty Django default and may have belonged to another app.
