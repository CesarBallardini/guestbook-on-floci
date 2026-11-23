# Security: the rules the guestbook keeps

The decisions that `docs/owasp.md` checks the guestbook against. Each rule names the file that
enforces it and the test that shows it. A change to a rule changes its row here, and the
rows of `docs/owasp.md` that cite it.

Paths that start with `domain/`, `use_cases/` or `infrastructure/` are under
`app/guestbook/`; test paths are under `app/`.

## 1. What a visitor may send

Everything a visitor sends is one of the items below. Anything else is refused, or, in a
URL, not found. The domain keeps the rules for a message (`app/guestbook/domain/`); the web
adapter and nginx keep the rules for a request.

| Item | Accepted when | Otherwise | Enforced in | Shown by |
|---|---|---|---|---|
| The name (`author`) | After trimming the spaces around it: 1 to 60 characters (`MAX_AUTHOR_LENGTH`), with no NUL character | 400, with the reason in plain text; nothing is stored | `domain/message.py`, `new_message` | `tests/unit/guestbook/domain/test_message.py` and `test_message_properties.py` |
| The text (`body`) | The same, 1 to 500 characters (`MAX_BODY_LENGTH`). Line breaks are kept | As the name | `domain/message.py`, `new_message` | As the name; line breaks in the e2e tests |
| The picture (`picture`) | Optional. Up to 2 MB (`MAX_PICTURE_BYTES`), and its first bytes are those of a PNG, JPEG, GIF or WebP file (`PICTURE_FORMATS`). The type and the file name the browser sends are ignored: the bytes decide | 400, with the reason; neither the message nor the picture is stored | `domain/picture.py`, `new_picture` | `tests/unit/guestbook/domain/test_picture.py` and `test_picture_properties.py` |
| The whole request | Up to 3 MB: room for a 2 MB picture and the form | 413 from nginx, with the app's own sentence about 2 MB, before the app sees it | `ansible/templates/nginx.conf.j2`, `client_max_body_size` | e2e: `test_a_picture_that_is_too_big_shows_the_same_reason_whoever_refuses_it` |
| The token of a post | The cookie `__Host-guestbook_csrf` and the form's `csrf_token` field, or the `X-CSRF-Token` header, are there and equal, compared in constant time. The page made the token: 32 random bytes | 403, before the message is looked at | `infrastructure/web/csrf.py`, `fastapi_app.py` | `tests/unit/guestbook/infrastructure/web/test_csrf.py` |
| A picture's key, in `/pictures/<key>` | 32 lowercase hexadecimal digits, one dot, and the extension of an accepted format | 404, without asking the storage | `domain/picture.py`, `is_picture_key`, from `use_cases/get_picture.py` | `tests/unit/guestbook/use_cases/test_get_picture.py`, `test_picture_properties.py` |

Every other form field is ignored. A message is shown as text, never as HTML: the templates
escape it (`test_what_a_visitor_writes_is_shown_as_text_not_as_html`, unit, and
`test_what_a_visitor_writes_is_shown_as_text_and_never_run`, e2e).

## 2. Limits, per visitor and for everybody

| Limit | Value | Enforced in | Shown by |
|---|---|---|---|
| Posts from one address | 2 a second on average, and up to 20 at once; above that, 429 with a sentence, from nginx. Reading is never limited | `nginx.conf.j2`, `limit_req`; the numbers are `signing_rate` and `signing_burst` in `ansible/playbook.yml` | e2e: `test_a_flood_of_posts_is_slowed_down_while_reading_goes_on` |
| Which address a post comes from | The one the load balancer puts in `X-Forwarded-For`, believed only when the connection comes from `load_balancer_cidr`. Otherwise the connection's own address | `nginx.conf.j2`, `set_real_ip_from` | No test |
| Messages on the page | The newest 50 | `use_cases/list_latest_messages.py` | `test_the_guestbook_shows_fifty_messages_unless_told_otherwise` |
| Posts from everybody together | No limit beyond each address's | | |
| Messages and pictures kept | No limit, and no expiry | | |

## 3. What the guestbook serves back

- **A picture, opened on its own,** comes with its format's type, `nosniff`,
  `Content-Security-Policy: default-src 'none'; sandbox` and
  `Cross-Origin-Resource-Policy: same-origin`. As a document of its own, a visitor's file
  can run nothing, load nothing and submit nothing, and no other site may embed it. The
  page's `<img>` is the same site, so it is unaffected. Enforced in
  `infrastructure/web/fastapi_app.py`, `picture`; shown by
  `test_a_picture_opened_on_its_own_can_run_nothing_and_load_nothing` (unit) and
  `test_signing_with_a_picture_updates_the_page_without_loading_it_again` (e2e: the headers
  through nginx, and the picture still drawn, on the page and in a tab of its own).
- **Every answer** carries HSTS, nginx's own 413 and 429 included (`nginx.conf.j2`).

## 4. Fixing known vulnerabilities, and keeping components current

**How fast a known vulnerability is fixed,** counted from the day its advisory is published,
by its CVSS base score:

| Severity | CVSS | Fixed within |
|---|---|---|
| Critical | 9.0 to 10.0 | 7 days |
| High | 7.0 to 8.9 | 30 days |
| Medium and low | Below 7.0 | 90 days |

"Fixed" means a merged pull request that moves the component to a release without the
vulnerability, or, where no such release exists yet, removes the vulnerable use or puts a
mitigation in front of it. If none of that is possible in time, the pull request that
would have fixed it says why, and when it will be looked at again.

**Updating in general:** every component is moved to its latest release at least every
quarter, even with no advisory against it. For the Python packages that is
`uv lock --upgrade` in `app/`, then the full check.

**The components, and what tells us about them:**

| Component | Pinned in | Watched by |
|---|---|---|
| The app's Python packages | `app/uv.lock`, with hashes | `pip-audit` in `make qa` (`make -C app security`) |
| Python, uv, certifi and pip | `app/.python-version`, `app/pyproject.toml`, `ansible/Dockerfile`, `ansible/playbook.yml`, `app/uv.lock` | `app/tests/unit/test_certificate_floors.py` keeps them at or above the eMudhra advisory's releases |
| Amazon Linux 2023, its Python, nginx, OpenVPN | `floci/image-catalog.yaml` (an image by digest) | Nothing yet |
| Floci and its console, the Ansible image's base | `compose.yaml`, `ansible/Dockerfile`, by digest or exact version | Nothing yet |
| Ansible and ansible-lint | `ansible/Dockerfile` | Nothing yet |
| Terraform's providers | `terraform/.terraform.lock.hcl` | Nothing yet |
| HTMX | A vendored copy in `infrastructure/web/static/` | Nothing yet |

"Nothing yet" ends with the CI that is planned: Dependabot for the Python packages, the
Actions and the Docker images, and a weekly `pip-audit`.
