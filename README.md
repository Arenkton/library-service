# Library Service API

A RESTful library management API built with **Django REST Framework** as a Mate Academy learning project. It manages readers, books, borrowings and returns, integrates **Stripe Checkout** for payments and overdue fines, and sends asynchronous **Telegram notifications** through Celery.

## Features

- **User management:** registration, email-based authentication, JWT access/refresh tokens, and profile management.
- **Book catalog:** public browsing and details; administrator-only management of titles, inventory, and daily fees.
- **Borrowings:** authenticated readers can borrow available books, view their history, and return books; administrators can manage all borrowings.
- **Inventory protection:** borrowing decreases available inventory, returning restores it, and repeated returns are rejected.
- **Borrowing filters:** filter by active/returned status; administrators can also filter by user.
- **Stripe payments:** Checkout Sessions for borrowing fees, payment tracking, success/cancel endpoints, and signature-verified webhooks.
- **Overdue fines:** fines based on overdue days, the book's daily fee, and a configurable multiplier; background creation and periodic recovery of missing fines.
- **Payment safeguards:** database uniqueness constraints, row locking for concurrent fine creation (PostgreSQL), and Stripe idempotency keys for fines.
- **Telegram notifications:** alerts for new borrowings, daily overdue reports, and successful payments.
- **Background processing:** Celery Worker and Celery Beat with Redis as the broker.
- **Developer tooling:** interactive Swagger documentation, Django tests, coverage reporting, and Flake8.

## Tech stack

| Component | Technology |
| --- | --- |
| Language and framework | Python 3.12+, Django 6.1, Django REST Framework 3.18 |
| Authentication | Simple JWT |
| API documentation | drf-spectacular / OpenAPI |
| Database | PostgreSQL in Docker; SQLite fallback for local development |
| Payments | Stripe Checkout and Webhooks |
| Background jobs | Celery, Celery Beat, Redis |
| Notifications | Telegram Bot API |
| Containers | Docker and Docker Compose |
| Dependency management | Poetry |
| Tests and linting | Django test runner, Coverage.py, Flake8 |

See [`pyproject.toml`](pyproject.toml) and [`poetry.lock`](poetry.lock) for dependency versions.

## Getting started with Docker (recommended)

### Prerequisites

Install [Git](https://git-scm.com/) and [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine with Docker Compose).

### 1. Clone the project

```bash
git clone https://github.com/Arenkton/library-service.git
cd library-service
```

Use the branch containing the latest payments implementation if it has not yet been merged into `main`.

### 2. Configure environment variables

Create a `.env` file from [`.env.example`](.env.example).

**Windows CMD:**

```cmd
copy .env.example .env
```

**macOS / Linux:**

```bash
cp .env.example .env
```

Set the necessary values in `.env`. For local development, a configuration may look like this (replace all example secrets with your own values):

```dotenv
DJANGO_SECRET_KEY=replace-with-a-generated-django-secret
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

STRIPE_SECRET_KEY=sk_test_replace_me
STRIPE_WEBHOOK_SECRET=whsec_replace_me
STRIPE_SUCCESS_URL=http://localhost:8001/payments/success/?session_id={CHECKOUT_SESSION_ID}
STRIPE_CANCEL_URL=http://localhost:8001/payments/cancel/
FINE_MULTIPLIER=2

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Generate a Django secret key with:

```cmd
poetry run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

This command requires Poetry and project dependencies to be installed locally; alternatively, generate a secret key with Django inside a running container.

The Telegram credentials are optional if you do not need notifications. Stripe test credentials are required to create real Checkout Sessions. The `STRIPE_WEBHOOK_SECRET` comes from the Stripe CLI listener or a configured Stripe webhook endpoint; it is **not** the Stripe API secret key.

**Security:** Never commit `.env`, live API keys, webhook secrets, or Telegram tokens. The included Compose configuration is for development, not production deployment.

### 3. Build and start the services

```bash
docker compose up --build -d
```

The Compose configuration starts:

- `web` — Django API (runs database migrations on startup)
- `db` — PostgreSQL
- `redis` — Redis broker
- `worker` — Celery Worker
- `beat` — Celery Beat scheduler

Check the containers:

```bash
docker compose ps
docker compose logs -f web
```

The API runs at **http://localhost:8001/**. Create an administrator account:

```bash
docker compose exec web python manage.py createsuperuser
```

The custom user model uses **email instead of username** for login.

### 4. Open the API documentation

| Resource | Docker URL |
| --- | --- |
| Swagger UI | http://localhost:8001/api/docs/ |
| OpenAPI schema | http://localhost:8001/api/schema/ |
| Django Admin | http://localhost:8001/admin/ |

Stop the services without deleting the database volume:

```bash
docker compose down
```

## Running without Docker

Install Python 3.12+ and [Poetry](https://python-poetry.org/docs/#installation), then run:

```bash
poetry install
poetry run python manage.py migrate
poetry run python manage.py runserver
```

Without `POSTGRES_HOST`, Django uses a local SQLite database. The API will be available at **http://127.0.0.1:8000/**.

For background processing, you must also provide a running Redis broker and start Celery Worker/Beat separately. PostgreSQL is recommended when testing concurrent operations because SQLite does not provide equivalent `select_for_update()` row-locking behavior. To use Stripe Checkout locally, configure valid Stripe test credentials and suitable redirect URLs for port `8000` instead of `8001`.

## Authentication

Obtain JWT tokens:

```http
POST /users/token/
Content-Type: application/json

{
  "email": "reader@example.com",
  "password": "your-password"
}
```

Pass the access token to protected endpoints:

```http
Authorize: Bearer <access_token>
```

**Important:** This project currently uses the nonstandard **`Authorize`** HTTP header (`HTTP_AUTHORIZE` in Django), **not** the usual `Authorization` header. In Swagger UI, use the **Authorize** control and supply the bearer token.

## API endpoints

### Users

| Method | Endpoint | Access | Description |
| --- | --- | --- | --- |
| `POST` | `/users/` | Public | Register a reader |
| `POST` | `/users/token/` | Public | Obtain JWT access and refresh tokens |
| `POST` | `/users/token/refresh/` | Valid refresh token | Refresh an access token |
| `GET` | `/users/me/` | Authenticated | View own profile |
| `PUT`, `PATCH` | `/users/me/` | Authenticated | Update own profile |

### Books

| Method | Endpoint | Access | Description |
| --- | --- | --- | --- |
| `GET` | `/books/` | Public | List books |
| `GET` | `/books/{id}/` | Public | Get book details |
| `POST` | `/books/` | Admin | Create a book |
| `PUT`, `PATCH` | `/books/{id}/` | Admin | Update a book |
| `DELETE` | `/books/{id}/` | Admin | Delete a book |

A book has a `title`, `author`, `cover` (`HARD` or `SOFT`), `inventory`, and positive decimal `daily_fee`.

### Borrowings

| Method | Endpoint | Access | Description |
| --- | --- | --- | --- |
| `GET` | `/borrowings/` | Authenticated | List accessible borrowings |
| `GET` | `/borrowings/{id}/` | Authenticated | Get borrowing details |
| `POST` | `/borrowings/` | Authenticated | Borrow an available book |
| `POST` | `/borrowings/{id}/return/` | Authenticated | Return a book |

Regular readers can access only their own borrowings; administrators can access all borrowings. Borrowings cannot be edited or deleted through the API.

**List filters:** `?is_active=true`, `?is_active=false`, and `?user_id=2` (staff only). They can be combined:

```http
GET /borrowings/?user_id=2&is_active=true
```

### Payments

| Method | Endpoint | Access | Description |
| --- | --- | --- | --- |
| `GET` | `/payments/` | Authenticated | List accessible payments |
| `GET` | `/payments/{id}/` | Authenticated | Retrieve a payment |
| `GET` | `/payments/success/` | Checkout redirect | Verify a completed Stripe Checkout Session |
| `GET` | `/payments/cancel/` | Checkout redirect | Handle cancelled Checkout flow |
| `POST` | `/payments/webhook/` | Stripe (signed request) | Process Stripe payment confirmations |

Readers can see their own payments, and administrators can see all payments. Payments are created by the borrowing/fine workflow rather than through a public `POST /payments/` endpoint.

Each payment stores a type (`PAYMENT` or `FINE`), status (`PENDING` or `PAID`), amount, and Stripe Checkout Session information (`session_id`, `session_url`). Follow the `session_url` to complete payment using Stripe Checkout.

The webhook verifies the Stripe signature and confirms payments only after validating the session details. Repeated confirmations do not change an already-paid payment or queue a new payment-success notification.

## Example borrowing and payment workflow

### 1. Register and authenticate

```http
POST /users/
Content-Type: application/json

{
  "email": "reader@example.com",
  "first_name": "Jane",
  "last_name": "Doe",
  "password": "StrongPassword123!"
}
```

Then obtain your access token using `POST /users/token/`.

### 2. Create a borrowing

```http
POST /borrowings/
Authorize: Bearer <access_token>
Content-Type: application/json

{
  "book": 1,
  "expected_return_date": "2030-01-01"
}
```

Use an existing book ID and a date later than the current date. The API sets `borrow_date` and the borrower automatically, decreases book inventory, and creates the borrowing payment and Stripe Checkout Session. The borrowing period must be positive.

### 3. Pay the borrowing fee

```http
GET /payments/
Authorize: Bearer <access_token>
```

Find the payment for your borrowing and open its `session_url`. Once Stripe confirms payment, the status becomes `PAID` and a Telegram notification is queued if configured.

### 4. Return the book

```http
POST /borrowings/1/return/
Authorize: Bearer <access_token>
```

The API records `actual_return_date` and restores one inventory item. The same borrowing cannot be returned twice. If the return is late, a Celery task creates an additional fine payment.

## Payment calculation and overdue fines

The borrowing fee is calculated as:

```text
borrowing_fee = daily_fee × borrowing_days
```

For an overdue return:

```text
overdue_days = actual_return_date - expected_return_date
fine = daily_fee × overdue_days × FINE_MULTIPLIER
```

For example, with a daily fee of **$1.50**, a return **3 days late**, and `FINE_MULTIPLIER=2`, the fine is **$9.00**. Amounts are charged in **USD** using Stripe Checkout.

A fine is created only for a returned, overdue borrowing. A regular payment and one fine payment may coexist for the same borrowing. Database constraints and Stripe idempotency keys reduce duplicate processing, and PostgreSQL row locking helps serialize concurrent fine creation.

Celery Beat also schedules an **hourly recovery task** that finds returned, overdue borrowings without a `FINE` payment and queues creation again. This allows the service to recover from some temporary task-queue or Stripe failures.

## Telegram notifications and scheduled tasks

With `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` configured, the service sends:

- A notification when a borrowing is created.
- Daily alerts for active overdue borrowings (scheduled for **09:00 UTC**).
- A notification when a Stripe payment changes from `PENDING` to `PAID`.

Celery Beat runs the overdue report daily and missing-fine recovery hourly. The `worker`, `beat`, and `redis` services must all be running for asynchronous and scheduled behavior to function.

Temporary Telegram failures are retried by Celery. A failed Telegram enqueue does not roll back an already-confirmed payment. Notifications are best-effort rather than guaranteed exactly-once delivery.

## Testing Stripe webhooks locally

Install the [Stripe CLI](https://docs.stripe.com/stripe-cli), authenticate, and start a listener:

```bash
stripe login
stripe listen --events checkout.session.completed,checkout.session.async_payment_succeeded --forward-to http://localhost:8001/payments/webhook/
```

Copy the CLI-provided `whsec_...` signing secret into `STRIPE_WEBHOOK_SECRET` in `.env` and restart the Django container so it reloads the configuration:

```bash
docker compose up -d --force-recreate web
```

You can now complete a **test-mode** Checkout payment using the returned `session_url`. The listener forwards signed events to the Django webhook. Use Stripe test credentials only; no real payments are needed for development.

The success redirect should include the Checkout Session ID if the success endpoint uses the `session_id` query parameter (Stripe supports the literal `{CHECKOUT_SESSION_ID}` placeholder in the configured success URL). The **signed webhook is the primary payment confirmation mechanism**.

## Tests and code quality

Run the full test suite:

```bash
poetry run python manage.py test
```

Run app tests:

```bash
poetry run python manage.py test users books borrowings payments notifications
```

Measure coverage:

```bash
poetry run python -m coverage erase
poetry run python -m coverage run manage.py test
poetry run python -m coverage report -m
```

Check formatting and Django configuration:

```bash
poetry run python -m flake8 .
poetry run python manage.py check
poetry run python manage.py makemigrations --check --dry-run
poetry run python manage.py spectacular --validate
```

The course target is **at least 60% test coverage**. Check the generated report for the actual coverage percentage.

## Project structure

```text
library-service/
├── books/             # Book models, serializers, views, and tests
├── borrowings/        # Borrowing workflows, filters, return logic, tests
├── users/             # Custom user model, JWT authentication, profile
├── payments/          # Stripe Checkout, webhooks, fines, recovery tasks
├── notifications/     # Telegram integration and Celery notifications
├── config/            # Django settings, URLs, Celery configuration
├── compose.yaml       # Django, PostgreSQL, Redis, Worker, and Beat
├── Dockerfile
├── manage.py
├── pyproject.toml
├── poetry.lock
├── .env.example
├── .coveragerc
├── .flake8
└── README.md
```

## Project scope and security notes

This is an educational backend project, not a production-ready payment platform. Docker Compose uses development credentials and Django's development server. Production deployment requires secure secret management, HTTPS, properly configured hosts, stronger infrastructure settings, and operational monitoring. For tests involving concurrent database updates, use PostgreSQL rather than SQLite.

Do not expose your Stripe secret key, Stripe webhook secret, Telegram bot token, or Django secret key in the repository or in screenshots.
