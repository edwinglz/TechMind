"""Follow-up questions must not repeat or rephrase what was already asked."""

from app.services.brief import drop_repeat_questions

OIL = "When was the oil last filtered or changed, and does it look very dark or smell burnt?"
TEMP = "What temperature does the display show compared with the set temperature, for example 350?"


def test_rephrased_questions_are_dropped():
    new = [{"question": "When was the oil last filtered or changed, and is it nearly black or does it smell burnt?"},
           {"question": "If the display is lit, what number does it show, and what is the set temperature?"},
           {"question": "Does the pilot flame stay lit after you let go of the knob?"},
           {"question": "Is the display blank?"},
           {"question": TEMP}]
    kept = [q["question"] for q in drop_repeat_questions(new, [OIL, TEMP], {OIL: {"answer": "no"}})]
    # The answered oil question can't come back in other words; the unanswered temperature
    # question may stay word for word but not as a rephrased copy; new topics stay.
    assert kept == ["Does the pilot flame stay lit after you let go of the knob?", "Is the display blank?", TEMP]


def test_answered_question_is_never_asked_again():
    assert drop_repeat_questions([{"question": OIL}], [OIL], {OIL: {"answer": "yes"}}) == []
