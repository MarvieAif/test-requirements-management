# aif-requirements

Lightweight helpers (`dsplus`) on top of [Doorstop](https://doorstop.readthedocs.io/) to create documents, seed headers, and add items with consistent attributes (UID, catalog id, created date, levels, etc.).

## Quick start

```bash
# 1) Create and activate a virtualenv (recommended)
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
# source venv/bin/activate

# 2) Install deps
pip install -r requirements.txt

# 3) Verify Doorstop is on PATH
doorstop --version
```

## Project layout (expected)

```
aif-requirements/
  catalog_config.yml           # global config (digits, sep, catalog UID prefix/width, etc.)
  catalog_registry.yml         # global counter + header lists
  catalog.yml                  # catalog index for seeded headers & items
  dsplus/
    __init__.py
    add.py                     # python -m dsplus.add ...
    create.py                  # python -m dsplus.create ...
    dsputils.py                # shared helpers (path + yaml utils)
  defaults/
    formfields.yml             # item defaults for normal requirements
    header.yml                 # item defaults for header requirements
  reqs/
    application-section/
      quickloan/
        contact-information/
          .doorstop.yml
          template/            # place your HTML templates here (see below)
            mybrand.tpl
            mybrand.css
            base.tpl           # (optional) see “Using mybrand.tpl”
```

## Using `mybrand.tpl` during publish

Doorstop copies any folder named `template/` that lives next to a document’s `.doorstop.yml` into the publish output and uses Bottle templates inside that folder when generating HTML.

There are two easy ways to make Doorstop use your `mybrand.tpl`:

**A. Replace the default base** (simple)
- Put your customized template at: `reqs/.../<doc>/template/base.tpl` (rename your file from `mybrand.tpl` → `base.tpl`), and put your CSS in `template/mybrand.css`.
- Run publish (no extra flags needed).

**B. Keep the file named `mybrand.tpl`** (no rename)
- Keep `template/mybrand.tpl` and add a thin `template/base.tpl` that simply rebases to it:
  ```tpl
  % rebase('mybrand.tpl')
  ```
- Run publish (no extra flags needed).

### Publish commands

Publish a single document (HTML) to a folder:

```bash
doorstop publish APP-QL-CNI ./dist/html/
```

Publish a single document (Markdown) to a file:

```bash
doorstop publish APP-QL-CNI ./dist/APP-QL-CNI.md
```

Publish all documents (HTML):

```bash
doorstop publish all ./dist/
```

> Doorstop auto-picks up the `template/` and `assets/` folders next to each document. Your `mybrand.tpl` and `mybrand.css` will be copied into `./dist/.../template/` and applied at render time.

## `dsplus` commands you’ll actually use

### Create a new document and seed standard headers

```bash
python -m dsplus.create APP-QL-CNI \
  --name contact-information \
  --type application \\  # uses headers.headers.application from catalog_registry.yml
  --title "Contact Information"
```

This creates `reqs/.../contact-information/.doorstop.yml`, patches defaults (title/by/version), and seeds headers from `catalog_registry.yml` → `headers.application` (e.g., “Form Fields”, “UI Behavior”, “Navigation”), writing each as a Header item.

### Add a header (bootstrap)

If you need to add a header by hand (rare), pass `--type header` to skip category checks and mark it as a header:

```bash
python -m dsplus.add APP-QL-CNI \
  --item_defaults defaults/header.yml \
  --title "Form Fields" \
  --type header
```

### Add a normal requirement under an existing header

```bash
python -m dsplus.add APP-QL-CNI \
  --root ./reqs \  --item_defaults defaults/formfields.yml \  --title "Customer must provide two phone numbers" \  --type "Form Fields"
```

Behavior:
- Validates that `--type` matches an existing seeded header (“Form Fields”, etc.); if it doesn’t, the script aborts with a helpful message.
- Computes the level as “1.X” under that header (first becomes 1.1, then 1.2, …).
- Fills attributes: `UID` (the Doorstop item id, e.g., `APP-QL-CNI-004`), `catalog_id` (global counter like `RQ-00012`), `created_date` (ISO), `form_id` (`APP-QL-CNI`), `form_name` (parent doc title, e.g., “Contact Information”), `header` (blank unless provided explicitly), `reviewed` (ISO today), and preserves/merges `links`.

## Core Doorstop commands (reference)

```bash
# Create a document
doorstop create APP-QL-CNI reqs/application-section/quickloan/contact-information --parent APP-QL

# Add a blank item (we wrap this in dsplus.add to auto-fill attributes)
doorstop add APP-QL-CNI -d defaults/formfields.yml

# Validate documents
doorstop validate

# Publish (HTML) with CSS
doorstop doorstop publish all ./published --template mybrand --index
```

## Troubleshooting

- **`ModuleNotFoundError: No module named 'dsplus'`** — Install the project in editable mode or call via the repo root:
  ```bash
  # from repo root
  python -m dsplus.create --help
  python -m dsplus.add --help
  ```
- **Publish doesn’t use your template** — Ensure `template/` folder is next to the `.doorstop.yml` of the document you’re publishing and that it contains a `base.tpl` (either your fully customized template, or a one-liner rebasing to `mybrand.tpl`).

---

**License**: Internal use.
