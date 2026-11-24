# Library Service API

A RESTful API for managing a small library: registering readers, maintaining a book catalog, borrowing available copies, and returning books. Built with Django REST Framework as a Mate Academy learning project.

## Features

- **User accounts:** registration, JWT login and token refresh, and profile viewing/updating.
- **Book catalog:** public listing and book details; administrator-only creation, editing, and deletion.
- **Borrowings:** authenticated readers can create borrowings and view their own borrowing history.
- **Availability control:** a successful borrowing decreases the book's inventory; a successful return restores one copy.
- **Return protection:** the same borrowing cannot be returned twice.
- **Borrowing filters:** filter by active/returned status; administrators can also filter by user.
- **Interactive API documentation:** Swagger UI and an OpenAPI schema.
- **Automated tests:** Django/DRF tests, coverage reporting, and Flake8 checks.

## Tech stack

- Python 3.12+
- Django 6.1
- Django REST Framework 3.18
- Simple JWT for authentication
- drf-spectacular for OpenAPI documentation
- SQLite (local database)
- Poetry for dependency management
- Coverage.py and Flake8 for quality checks

Exact dependency versions are specified in [`pyproject.toml`](pyproject.toml) and locked in [`poetry.lock`](poetry.lock).

## Getting started

### Prerequisites

Install [Python](https://www.python.org/downloads/) (3.12 or newer), [Git](https://git-scm.com/), and [Poetry](https://python-poetry.org/docs/#installation).

### 1. Clone and install

```bash
git clone https://github.com/Arenkton/library-service.git
cd library-service
poetry install
```

### 2. Configure environment variables

Create a `.env` file from the committed example:

**Windows CMD:**

```cmd
copy .env.example .env
```

**macOS / Linux:**

```bash
cp .env.example .env
```

Generate a development secret key if needed:

```bash
poetry run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Set the variables in `.env`:

```dotenv
DJANGO_SECRET_KEY=replace-with-your-generated-secret-key
DJANGO_DEBUG=True
```

`DJANGO_DEBUG=True` is intended **only for local development**. The current project configuration uses an empty `ALLOWED_HOSTS` list and is not production-ready without additional deployment/security settings. Never commit your real `.env` file or secret key.

### 3. Apply migrations and start the server

```bash
poetry run python manage.py migrate
poetry run python manage.py runserver
```

The API is available at `http://127.0.0.1:8000/`.

To create an administrator account:

```bash
poetry run python manage.py createsuperuser
```

The custom user model uses **email**, not username, for login.

## API documentation

With the development server running:

- **Swagger UI:** http://127.0.0.1:8000/api/docs/
- **OpenAPI schema:** http://127.0.0.1:8000/api/schema/
- **Django Admin:** http://127.0.0.1:8000/admin/

### Authentication: important header name

Request a JWT access and refresh token:

```http
POST /users/token/
Content-Type: application/json

{
  "email": "reader@example.com",
  "password": "your-password"
}
```

Use the access token for protected endpoints:

```http
Authorize: Bearer <access_token>
```

**Important:** This project is configured to read the **`Authorize`** HTTP header, **not** the usual `Authorization` header. In Swagger UI, click **Authorize** and enter `Bearer <access_token>`.

## Endpoints

### Users

| Method | Endpoint | Access | Description |
| --- | --- | --- | --- |
| `POST` | `/users/` | Public | Register an account |
| `POST` | `/users/token/` | Public | Obtain JWT access and refresh tokens |
| `POST` | `/users/token/refresh/` | Public (valid refresh token required) | Refresh an access token |
| `GET` | `/users/me/` | Authenticated | Get current user profile |
| `PUT`, `PATCH` | `/users/me/` | Authenticated | Update current user profile |

### Books

| Method | Endpoint | Access | Description |
| --- | --- | --- | --- |
| `GET` | `/books/` | Public | List books |
| `GET` | `/books/{id}/` | Public | Retrieve book details |
| `POST` | `/books/` | Admin | Add a book |
| `PUT`, `PATCH` | `/books/{id}/` | Admin | Update a book |
| `DELETE` | `/books/{id}/` | Admin | Delete a book |

A book has `title`, `author`, `cover` (`HARD` or `SOFT`), `inventory` (available copies), and `daily_fee` (positive decimal amount).

### Borrowings

| Method | Endpoint | Access | Description |
| --- | --- | --- | --- |
| `GET` | `/borrowings/` | Authenticated | List accessible borrowings |
| `GET` | `/borrowings/{id}/` | Authenticated | Get an accessible borrowing |
| `POST` | `/borrowings/` | Authenticated | Borrow a book |
| `POST` | `/borrowings/{id}/return/` | Authenticated | Return a borrowed book |

Regular users can access **only their own** borrowings. Staff administrators can view and return borrowings belonging to any user. Borrowings cannot be edited or deleted through the API.

#### List filters

| Query parameter | Example | Description |
| --- | --- | --- |
| `is_active` | `?is_active=true` | Borrowings that have not been returned |
| `is_active` | `?is_active=false` | Returned borrowings |
| `user_id` | `?user_id=2` | Filter by borrower; applied for staff users only |

Filters can be combined, for example:

```http
GET /borrowings/?user_id=2&is_active=true
```

For regular users, the `user_id` filter does not override the restriction to their own borrowings.

## Example workflow

### 1. Register a reader

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

Obtain an access token using `POST /users/token/` as shown above.

### 2. Find a book

```http
GET /books/
```

An administrator can add a book:

```http
POST /books/
Authorize: Bearer <admin_access_token>
Content-Type: application/json

{
  "title": "Dune",
  "author": "Frank Herbert",
  "cover": "SOFT",
  "inventory": 5,
  "daily_fee": "2.50"
}
```

### 3. Create a borrowing

```http
POST /borrowings/
Authorize: Bearer <access_token>
Content-Type: application/json

{
  "book": 1,
  "expected_return_date": "2030-01-01"
}
```

Replace `1` with an existing book ID and choose an **expected return date later than today**. The API attaches the authenticated user and sets the borrowing date automatically. The book must have at least one available copy; successful creation decreases its inventory by one.

### 4. Review and return the borrowing

```http
GET /borrowings/?is_active=true
Authorize: Bearer <access_token>
```

Return a borrowing using its ID (there is no JSON request body):

```http
POST /borrowings/1/return/
Authorize: Bearer <access_token>
```

A successful return sets `actual_return_date` to the current application date and increases the book inventory by one. A second return attempt is rejected.

## Data model

- **User:** custom Django user with unique email as the login identifier.
- **Book:** catalog entry with format, available inventory, and daily fee.
- **Borrowing:** references a `User` and a `Book`, and stores `borrow_date`, `expected_return_date`, and optional `actual_return_date`.

An active borrowing has `actual_return_date = null`. The expected return date must be after the borrowing date. Inventory adjustments and borrowing/return updates use database transactions and conditional updates to prevent inconsistent state.

## Tests and code quality

Run all automated tests:

```bash
poetry run python manage.py test
```

Run individual app tests:

```bash
poetry run python manage.py test users books borrowings
```

Measure coverage (configured in [`.coveragerc`](.coveragerc)):

```bash
poetry run python -m coverage erase
poetry run python -m coverage run manage.py test
poetry run python -m coverage report -m
```

Run linting and configuration checks:

```bash
poetry run python -m flake8 borrowings users books config
poetry run python manage.py check
poetry run python manage.py makemigrations --check --dry-run
poetry run python manage.py spectacular --validate
```

The project aims to meet the course requirement of **at least 60% test coverage**. Consult the generated coverage report for the actual measured percentage; no fixed figure is claimed here.

## Project structure

```text
library-service/
├── books/           # Book model, serializers, views, admin, tests
├── borrowings/      # Borrowing model, creation/return logic, filters, tests
├── users/           # Custom email-based user, JWT endpoints, profile, tests
├── config/          # Django settings and root URL configuration
├── manage.py
├── pyproject.toml   # Dependencies and Poetry configuration
├── poetry.lock
├── .env.example     # Example local environment variables
├── .coveragerc      # Coverage settings
├── .flake8          # Lint settings
└── README.md
```

## Scope

This repository implements user management, book management, borrowing creation and history, filtering, and returns. It uses a local SQLite database and is intended as an API-focused learning project. Payment processing, external notifications, and production deployment are outside the implemented scope.
