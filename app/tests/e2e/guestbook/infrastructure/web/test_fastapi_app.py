"""End-to-end tests: a real browser against the deployed guestbook, through the load balancer.

They enter where a visitor does, the web adapter, and go through every layer down to the
emulated RDS and S3, with nginx in between. They need the whole stack up and the playbook run.
GUESTBOOK_URL and GUESTBOOK_HTTP_URL choose other addresses. Each run leaves a few messages in
the guestbook, with texts that tell the runs apart.
"""

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx2 as httpx
import pytest
from playwright.sync_api import Browser, Page, Route, expect

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.e2e

GUESTBOOK_URL = os.environ.get('GUESTBOOK_URL', 'https://localhost:8443/')
GUESTBOOK_HTTP_URL = os.environ.get('GUESTBOOK_HTTP_URL', 'http://localhost:8080/')
MEGABYTE = 1024 * 1024
# Well over what one address may post at once (the playbook's signing_burst, 20).
FLOOD_POSTS = 80
# signing_burst divided by signing_rate (2 a second), and a little more.
SECONDS_UNTIL_THE_FLOOD_IS_FORGOTTEN = 11


@pytest.fixture(scope='session')
def browser_context_args(browser_context_args: dict[str, object]) -> dict[str, object]:
    # The emulator's certificate comes from an issuer of its own.
    return {**browser_context_args, 'ignore_https_errors': True}


def a_text_of_this_run(start: str) -> str:
    return f'{start} {uuid.uuid4().hex}'


def test_signing_with_a_picture_updates_the_page_without_loading_it_again(
    page: Page, tmp_path: Path, png_bytes: bytes
) -> None:
    picture_file = tmp_path / 'pixel.png'
    picture_file.write_bytes(png_bytes)
    body = a_text_of_this_run('End-to-end greetings')

    page.goto(GUESTBOOK_URL)
    page.evaluate('window.loadedOnce = true')
    page.get_by_placeholder('Your name').fill('Playwright')
    page.get_by_placeholder('Your message').fill(body)
    page.locator('input[name="picture"]').set_input_files(picture_file)
    page.get_by_role('button', name='Sign the guestbook').click()

    newest = page.locator('#messages li').first
    expect(newest.locator('.body')).to_have_text(body)
    expect(newest.locator('.meta')).to_contain_text('Playwright, ')
    # The picture came back from S3 and the browser could draw it.
    picture = newest.locator('img')
    expect(picture).to_be_visible()
    assert picture.evaluate('image => image.decode().then(() => image.naturalWidth)') == 1
    # HTMX swapped the list in place: the page was not loaded again, and the form was emptied.
    assert page.evaluate('window.loadedOnce') is True
    expect(page.get_by_placeholder('Your message')).to_have_value('')

    page.reload()
    expect(page.locator('#messages li .body').first).to_have_text(body)


def test_a_refused_message_shows_the_reason(page: Page, tmp_path: Path) -> None:
    not_an_image = tmp_path / 'notes.png'
    not_an_image.write_text('Just some notes.')

    page.goto(GUESTBOOK_URL)
    page.get_by_placeholder('Your name').fill('Playwright')
    page.get_by_placeholder('Your message').fill('This one must not appear')
    page.locator('input[name="picture"]').set_input_files(not_an_image)
    page.get_by_role('button', name='Sign the guestbook').click()

    expect(page.get_by_role('alert')).to_have_text('A picture must be a PNG, JPEG, GIF or WebP image.')
    expect(page.locator('#messages')).not_to_contain_text('This one must not appear')


@pytest.mark.parametrize(
    'megabytes',
    [
        pytest.param(2.5, id='over-the-apps-limit-and-under-nginxs'),
        pytest.param(4, id='over-nginxs-limit'),
    ],
)
def test_a_picture_that_is_too_big_shows_the_same_reason_whoever_refuses_it(
    page: Page, tmp_path: Path, png_bytes: bytes, megabytes: float
) -> None:
    # The app refuses pictures over 2 MB; nginx, in front of it, refuses requests over 3 MB
    # before the app sees them. The visitor must read the same sentence either way.
    big_picture = tmp_path / 'big.png'
    big_picture.write_bytes(png_bytes.ljust(int(megabytes * MEGABYTE), b'\0'))
    body = a_text_of_this_run('Too big a picture')

    page.goto(GUESTBOOK_URL)
    page.get_by_placeholder('Your name').fill('Playwright')
    page.get_by_placeholder('Your message').fill(body)
    page.locator('input[name="picture"]').set_input_files(big_picture)
    page.get_by_role('button', name='Sign the guestbook').click()

    expect(page.get_by_role('alert')).to_have_text('A picture can have up to 2 MB.')
    expect(page.locator('#messages')).not_to_contain_text(body)
    # What the visitor wrote is still there to send again with another picture.
    expect(page.get_by_placeholder('Your message')).to_have_value(body)


def test_signing_works_in_a_browser_without_javascript(browser: Browser) -> None:
    body = a_text_of_this_run('No JavaScript here')
    context = browser.new_context(ignore_https_errors=True, java_script_enabled=False)
    try:
        page = context.new_page()
        page.goto(GUESTBOOK_URL)
        page.get_by_placeholder('Your name').fill('Playwright')
        page.get_by_placeholder('Your message').fill(body)
        page.get_by_role('button', name='Sign the guestbook').click()

        # The plain form post was answered with a redirect back to the page.
        expect(page).to_have_url(GUESTBOOK_URL)
        expect(page.locator('#messages li .body').first).to_have_text(body)
    finally:
        context.close()


def test_the_guestbook_works_over_plain_http_too(page: Page) -> None:
    body = a_text_of_this_run('Over plain HTTP')

    page.goto(GUESTBOOK_HTTP_URL)
    page.get_by_placeholder('Your name').fill('Playwright')
    page.get_by_placeholder('Your message').fill(body)
    page.get_by_role('button', name='Sign the guestbook').click()

    expect(page.locator('#messages li .body').first).to_have_text(body)


def test_a_guestbook_that_cannot_be_reached_says_so_and_keeps_what_was_written(page: Page) -> None:
    body = a_text_of_this_run('Sent into the void')

    page.goto(GUESTBOOK_URL)
    # From here on, the post never gets an answer: the network fails.
    page.route('**/messages', lambda route: route.abort())
    page.get_by_placeholder('Your name').fill('Playwright')
    page.get_by_placeholder('Your message').fill(body)
    page.get_by_role('button', name='Sign the guestbook').click()

    expect(page.get_by_role('alert')).to_have_text('The guestbook could not be reached. Please try again.')
    expect(page.get_by_placeholder('Your message')).to_have_value(body)
    # The button works again for the next try.
    expect(page.get_by_role('button', name='Sign the guestbook')).to_be_enabled()


def test_the_button_is_off_while_a_message_is_on_its_way(page: Page) -> None:
    page.goto(GUESTBOOK_URL)
    held_routes: list[Route] = []

    def hold(route: Route) -> None:
        held_routes.append(route)

    page.route('**/messages', hold)
    page.get_by_placeholder('Your name').fill('Playwright')
    page.get_by_placeholder('Your message').fill(a_text_of_this_run('Sent once'))
    button = page.get_by_role('button', name='Sign the guestbook')
    button.click()

    # A second click can't send the message twice.
    expect(button).to_be_disabled()
    held_routes[0].continue_()
    expect(button).to_be_enabled()


def test_a_message_keeps_its_line_breaks_on_the_page(page: Page) -> None:
    first_line = a_text_of_this_run('First line')

    page.goto(GUESTBOOK_URL)
    page.get_by_placeholder('Your name').fill('Playwright')
    page.get_by_placeholder('Your message').fill(f'{first_line}\nSecond line')
    page.get_by_role('button', name='Sign the guestbook').click()

    newest_body = page.locator('#messages li .body').first
    expect(newest_body).to_contain_text(first_line)
    # innerText is the text as it is drawn: the break is there only if the page shows it.
    assert newest_body.inner_text() == f'{first_line}\nSecond line'


def test_what_a_visitor_writes_is_shown_as_text_and_never_run(page: Page) -> None:
    body = f'<img src=x onerror="window.gotcha = \'{uuid.uuid4().hex}\'">'

    page.goto(GUESTBOOK_URL)
    page.get_by_placeholder('Your name').fill('Playwright')
    page.get_by_placeholder('Your message').fill(body)
    page.get_by_role('button', name='Sign the guestbook').click()

    newest = page.locator('#messages li').first
    expect(newest.locator('.body')).to_have_text(body)
    assert newest.locator('img').count() == 0
    assert page.evaluate('window.gotcha') is None


def test_a_flood_of_posts_is_slowed_down_while_reading_goes_on() -> None:
    # Kept last in this file: it uses up what one address may post at once, and then waits
    # for nginx to forget, so that the next run starts with nothing held against it.
    # The posts carry no token, so those that get through are refused by the app: nothing is
    # stored either way.
    def post_a_message(_number: int) -> httpx.Response:
        return client.post('messages', data={'author': 'Flood', 'body': 'Again and again'})

    with httpx.Client(base_url=GUESTBOOK_HTTP_URL) as client:
        with ThreadPoolExecutor(max_workers=20) as executor:
            answers = list(executor.map(post_a_message, range(FLOOD_POSTS)))
        reading = client.get('')

    got_through = [answer for answer in answers if answer.status_code == HTTPStatus.FORBIDDEN]
    slowed_down = [answer for answer in answers if answer.status_code == HTTPStatus.TOO_MANY_REQUESTS]
    assert len(got_through) + len(slowed_down) == FLOOD_POSTS
    # Some get through, as a person's posts do; most of a flood does not.
    assert got_through
    assert len(slowed_down) > FLOOD_POSTS // 2
    assert slowed_down[0].text == 'Too many messages in a short time. Please wait a moment and try again.\n'
    assert reading.status_code == HTTPStatus.OK

    time.sleep(SECONDS_UNTIL_THE_FLOOD_IS_FORGOTTEN)
