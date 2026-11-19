"""Property-based tests for the rules for messages: they hold for any text, not only the examples."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from guestbook.domain.errors import InvalidMessageError
from guestbook.domain.message import MAX_AUTHOR_LENGTH, MAX_BODY_LENGTH, new_message

pytestmark = pytest.mark.unit

# Long enough to go over both limits, and likely to bring spaces around.
any_text = st.text(max_size=MAX_BODY_LENGTH + 50)
spaces = st.text(alphabet=' \t\n', max_size=5)
# Texts the rules can accept: no spaces around, and no NUL character.
acceptable_characters = st.characters(exclude_characters='\x00')


@given(author=any_text, body=any_text)
def test_a_message_is_either_accepted_within_the_rules_or_refused(author: str, body: str) -> None:
    try:
        message = new_message(author, body)
    except InvalidMessageError:
        assert (
            not 1 <= len(author.strip()) <= MAX_AUTHOR_LENGTH
            or not 1 <= len(body.strip()) <= MAX_BODY_LENGTH
            or '\x00' in author + body
        )
    else:
        assert '\x00' not in message.author + message.body
        assert message.author == author.strip()
        assert message.body == body.strip()
        assert 1 <= len(message.author) <= MAX_AUTHOR_LENGTH
        assert 1 <= len(message.body) <= MAX_BODY_LENGTH
        assert message.picture is None


@given(
    author=st.text(acceptable_characters, min_size=1, max_size=MAX_AUTHOR_LENGTH).filter(
        lambda text: text == text.strip()
    ),
    body=st.text(acceptable_characters, min_size=1, max_size=MAX_BODY_LENGTH).filter(
        lambda text: text == text.strip()
    ),
    before=spaces,
    after=spaces,
)
def test_spaces_around_the_texts_never_change_the_message(author: str, body: str, before: str, after: str) -> None:
    assert new_message(before + author + after, before + body + after) == new_message(author, body)


@given(author=any_text, body=any_text)
def test_a_message_that_was_accepted_is_accepted_again_unchanged(author: str, body: str) -> None:
    try:
        message = new_message(author, body)
    except InvalidMessageError:
        return

    assert new_message(message.author, message.body) == message
