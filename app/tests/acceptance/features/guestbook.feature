@bdd
Feature: Signing the guestbook
  As a visitor
  I want to leave a message, with a picture if I like
  So that the next visitors can see I was here

  Scenario: A new guestbook has no messages
    Given an empty guestbook
    When I open the guestbook
    Then I see that there are no messages yet

  Scenario: Signing shows my message
    Given an empty guestbook
    When "Ada" signs with the message "Greetings from the lab"
    Then the guestbook shows "Greetings from the lab" by "Ada"

  Scenario: The newest message comes first
    Given an empty guestbook
    And "Ada" signs with the message "I was first"
    When "Bob" signs with the message "I came later"
    Then "I came later" is shown before "I was first"

  Scenario: Signing with a picture shows the picture
    Given an empty guestbook
    When "Ada" signs with the message "My cat" and a picture
    Then the guestbook shows "My cat" by "Ada"
    And the message has a picture that can be downloaded

  Scenario: A message without a name is refused
    Given an empty guestbook
    When "" signs with the message "Anonymous greetings"
    Then the message is refused because "needs a name"
    And I see that there are no messages yet

  Scenario: A file that is not an image is refused
    Given an empty guestbook
    When "Ada" signs with the message "My notes" and a text file as picture
    Then the message is refused because "must be a PNG, JPEG, GIF or WebP image"
    And I see that there are no messages yet

  Scenario: A message that is too long is refused
    Given an empty guestbook
    When "Ada" signs with a message of 501 characters
    Then the message is refused because "needs a text of 1 to 500 characters"
    And I see that there are no messages yet

  Scenario: A message as long as allowed is accepted
    Given an empty guestbook
    When "Ada" signs with a message of 500 characters
    Then the guestbook shows 1 message

  Scenario: A picture that is too big is refused
    Given an empty guestbook
    When "Ada" signs with the message "My holidays" and a picture of 3 MB
    Then the message is refused because "A picture can have up to 2 MB"
    And I see that there are no messages yet

  Scenario: The guestbook shows the latest 50 messages
    Given an empty guestbook
    And 51 visitors signed, one after the other
    When I open the guestbook
    Then the guestbook shows 50 messages
    And the guestbook shows "Greetings from visitor 51" by "Visitor 51"
    And the guestbook does not show "Greetings from visitor 1."

  Scenario: What a visitor writes is never run as part of the page
    Given an empty guestbook
    When "Ada" signs with the message "<script>alert('gotcha')</script>"
    Then the page has no script written by a visitor

  Scenario: The guestbook says so when its messages cannot be reached
    Given a guestbook whose messages cannot be reached
    When "Ada" signs with the message "Is anybody there?"
    Then I am told that the guestbook is not available right now

  Scenario: A message without picture is accepted while the pictures cannot be reached
    Given a guestbook whose pictures cannot be reached
    When "Ada" signs with the message "No picture today"
    Then the guestbook shows "No picture today" by "Ada"
