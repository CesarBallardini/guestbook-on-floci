"""Protection against forged posts: a token only the visitor's own page knows.

A page of another site can make a browser post a form to the guestbook. It cannot read the
guestbook's cookie, nor the page the guestbook served. So the guestbook gives each browser a
random token twice, in a cookie and inside the form, and accepts a post only when both come
back and are the same. The form sends it as a field; a script may send it as a header instead.

The guestbook has no accounts, so nothing here says who the visitor is: the token only shows
that the post comes from a page the guestbook itself served to this browser.
"""

import hmac
import secrets

# The "__Host-" prefix: a browser keeps the cookie only if it came over HTTPS, is marked Secure,
# names no domain and is for every path. So no other host, not even a subdomain, can set it.
CSRF_COOKIE_NAME = '__Host-guestbook_csrf'
CSRF_FIELD_NAME = 'csrf_token'
CSRF_HEADER_NAME = 'X-CSRF-Token'
_TOKEN_BYTES = 32


def new_csrf_token() -> str:
    """Make a token nobody can guess."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def csrf_tokens_match(cookie_token: str | None, sent_token: str | None) -> bool:
    """Tell whether a post carries the token its browser was given. Missing tokens never match."""
    if not cookie_token or not sent_token:
        return False
    # Compared in constant time: how long it takes says nothing about where they differ.
    return hmac.compare_digest(cookie_token.encode(), sent_token.encode())
