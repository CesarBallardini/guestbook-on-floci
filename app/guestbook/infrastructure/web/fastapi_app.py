"""The guestbook's web side: one page, made with FastAPI and HTMX.

It is an input adapter: it turns HTTP requests into calls on the guestbook's input ports and
knows nothing of what is behind them.

The form posts in the background, and the server answers with the list of messages only, which
replaces the one on the page.

The handlers are plain functions, not coroutines: FastAPI runs them in a thread pool, which
suits the blocking PostgreSQL and S3 clients behind the ports.
"""

import logging
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from guestbook.domain.errors import InvalidMessageError, StorageError
from guestbook.domain.input_ports import SignGuestbookRequestDto
from guestbook.domain.message import MAX_AUTHOR_LENGTH, MAX_BODY_LENGTH
from guestbook.domain.picture import MAX_PICTURE_BYTES, MAX_PICTURE_MEGABYTES, PICTURE_FORMATS, accepted_format_names
from guestbook.infrastructure.web.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_FIELD_NAME,
    CSRF_HEADER_NAME,
    csrf_tokens_match,
    new_csrf_token,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Sequence
    from datetime import datetime

    from guestbook.domain.input_ports import GetPicturePort, ListLatestMessagesPort, SignGuestbookPort

_WEB_DIR = Path(__file__).parent
_logger = logging.getLogger(__name__)


def _datetime_utc_as_str(a_datetime_utc: datetime) -> str:
    return a_datetime_utc.strftime('%Y-%m-%d %H:%M:%S UTC')


def create_fastapi_app(
    sign_guestbook_port: SignGuestbookPort,
    list_latest_messages_port: ListLatestMessagesPort,
    get_picture_port: GetPicturePort,
    startup_checks: Sequence[Callable[[], None]] = (),
) -> FastAPI:
    """Build the web application on top of the guestbook's three input ports.

    Args:
        sign_guestbook_port: Signs the guestbook.
        list_latest_messages_port: Lists the latest messages.
        get_picture_port: Gets a picture.
        startup_checks: Run in order when the app starts, before it serves anything. One that
            raises stops the start.
    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        # Run once per worker, when it starts: not when the app is put together, which
        # connects to nothing.
        for startup_check in startup_checks:
            startup_check()
        yield

    # A page for people, not an API for programs: no generated API documentation.
    app = FastAPI(title='Guestbook', docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.mount('/static', StaticFiles(directory=_WEB_DIR / 'static'), name='static')
    templates = Jinja2Templates(directory=_WEB_DIR / 'templates')
    templates.env.filters['as_str'] = _datetime_utc_as_str

    @app.exception_handler(StorageError)
    def storage_failed(request: Request, error: StorageError) -> PlainTextResponse:
        # The cause goes to the server's log; a visitor only needs to know it isn't their fault.
        _logger.error('%s %s failed: %s', request.method, request.url.path, error, exc_info=error)
        return PlainTextResponse(
            'The guestbook is not available right now. Please try again later.\n', status_code=503
        )

    @app.get('/')
    def index(request: Request) -> Response:
        csrf_token = request.cookies.get(CSRF_COOKIE_NAME) or new_csrf_token()
        response = templates.TemplateResponse(
            request,
            'page.html',
            {
                'csrf_field_name': CSRF_FIELD_NAME,
                'csrf_token': csrf_token,
                'messages': list_latest_messages_port.list_latest_messages(),
                'instance_name': socket.gethostname(),
                'max_author_length': MAX_AUTHOR_LENGTH,
                'max_body_length': MAX_BODY_LENGTH,
                'max_picture_megabytes': MAX_PICTURE_MEGABYTES,
                'accepted_format_names': accepted_format_names(),
                'accepted_content_types': ','.join(picture_format.content_type for picture_format in PICTURE_FORMATS),
            },
        )
        # No script may read it, the browser sends it with the guestbook's own pages only, and
        # only over HTTPS. The app itself sees plain HTTP from the load balancer; the browser
        # does not, and that is what the attribute is for.
        response.set_cookie(CSRF_COOKIE_NAME, csrf_token, secure=True, httponly=True, samesite='strict')
        return response

    @app.post('/messages')
    def post_message(
        request: Request,
        author: Annotated[str, Form()] = '',
        body: Annotated[str, Form()] = '',
        picture: UploadFile | None = None,
        csrf_token: Annotated[str | None, Form()] = None,
    ) -> Response:
        sent_token = csrf_token or request.headers.get(CSRF_HEADER_NAME)
        if not csrf_tokens_match(request.cookies.get(CSRF_COOKIE_NAME), sent_token):
            return PlainTextResponse(
                'This page is out of date. Please load it again, then sign the guestbook.\n', status_code=403
            )
        # One byte over the limit is enough for the rules to see the picture is too big.
        picture_content = picture.file.read(MAX_PICTURE_BYTES + 1) if picture else b''
        try:
            sign_guestbook_port.sign_guestbook(SignGuestbookRequestDto(author, body, picture_content))
        except InvalidMessageError as error:
            return PlainTextResponse(f'{error}\n', status_code=400)
        if request.headers.get('HX-Request'):
            return templates.TemplateResponse(
                request, 'messages.html', {'messages': list_latest_messages_port.list_latest_messages()}
            )
        return RedirectResponse('/', status_code=303)  # a browser without JavaScript

    @app.get('/pictures/{picture_key}')
    def picture(picture_key: str) -> Response:
        stored = get_picture_port.get_picture(picture_key)
        if stored is None:
            raise HTTPException(status_code=404)
        return Response(
            stored.content,
            media_type=stored.content_type,
            headers={
                # A key never gets another picture, so the browser may keep it.
                'Cache-Control': 'private, max-age=31536000, immutable',
                'X-Content-Type-Options': 'nosniff',
                # A visitor's file, opened as a page of its own, can run nothing and load
                # nothing; and only this site may embed it. The page's <img> is unaffected.
                'Content-Security-Policy': "default-src 'none'; sandbox",
                'Cross-Origin-Resource-Policy': 'same-origin',
            },
        )

    @app.get('/health')
    def health() -> PlainTextResponse:
        return PlainTextResponse('ok\n')

    return app
