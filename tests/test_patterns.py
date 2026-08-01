"""Tests for the ELIZA-style pattern engine."""
from __future__ import annotations

import pytest

from shaggoth.dialogue.patterns import PatternEngine, reflect, RULES, REFLECTIONS


class TestReflect:
    def test_first_person_to_second(self):
        assert reflect("i am happy") == "you are happy"

    def test_second_person_to_first(self):
        assert reflect("you are right") == "I am right"

    def test_my_to_your(self):
        assert reflect("my name") == "your name"

    def test_your_to_my(self):
        assert reflect("your idea") == "my idea"

    def test_contraction_im(self):
        assert reflect("i'm fine") == "you're fine"

    def test_unknown_words_pass_through(self):
        assert reflect("aeroponic hydroponics") == "aeroponic hydroponics"

    def test_trailing_punctuation_stripped(self):
        # reflect() strips trailing .!? from the fragment
        assert reflect("i am!") == "you are"

    def test_empty_string(self):
        assert reflect("") == ""

    def test_mixed_case_preserved_for_unknown(self):
        result = reflect("Shaggoth knows")
        assert "Shaggoth" in result

    def test_bigram_you_are_becomes_i_am(self):
        assert reflect("you are wrong") == "I am wrong"
        assert reflect("you are the best") == "I am the best"

    def test_bigram_i_am_becomes_you_are(self):
        assert reflect("i am tired") == "you are tired"


class TestPatternEngine:
    def setup_method(self):
        self.engine = PatternEngine(seed=42)

    def test_returns_none_on_no_match(self):
        # A very specific string that matches no rule
        assert self.engine.respond("xyzzy frobnicator") is None

    def test_greeting_rules_match(self):
        for word in ("hello", "hi", "hey", "howdy", "yo"):
            result = self.engine.respond(f"{word} there")
            assert result is not None, f"Should match greeting: {word!r}"

    def test_name_rule_captures_and_reflects(self):
        result = self.engine.respond("my name is Alice")
        assert result is not None
        assert "Alice" in result

    def test_i_need_captures_and_reflects(self):
        result = self.engine.respond("I need more coffee")
        assert result is not None
        assert "coffee" in result.lower()

    def test_i_need_skips_practical_requests(self):
        assert self.engine.respond("I need to install Python") is None
        assert self.engine.respond("I need help with my code") is None
        assert self.engine.respond("I need a way to fix this") is None
        assert self.engine.respond("I need some information about gravity") is None

    def test_i_need_help_with_trailing_punctuation_routes_to_help(self):
        # Regression: the trailing period previously broke the negative lookahead,
        # so "I need help." fell through to the generic "what do you need X for?"
        # reply instead of the dedicated help-request rule.
        result = self.engine.respond("I need help.")
        assert result is not None
        assert "knowledge base" in result.lower()

    def test_i_am_sad_matches(self):
        result = self.engine.respond("I am feeling sad")
        assert result is not None
        assert "sad" in result.lower()

    def test_i_am_happy_matches(self):
        result = self.engine.respond("I'm happy today")
        assert result is not None

    def test_i_am_building_captures(self):
        result = self.engine.respond("I am building a homelab server")
        assert result is not None
        # The captured group should appear in the reply
        assert "homelab server" in result

    def test_i_like_captures(self):
        result = self.engine.respond("I like synthwave music")
        assert result is not None
        assert "synthwave music" in result

    def test_i_think_captures(self):
        result = self.engine.respond("I think this is wrong")
        assert result is not None

    def test_i_think_skips_self_referential_intent(self):
        assert self.engine.respond("I think I need to go") is None
        assert self.engine.respond("I think I should leave") is None
        assert self.engine.respond("I think I'm going to bed") is None

    def test_who_are_you_matches_self_awareness(self):
        result = self.engine.respond("Who are you?")
        assert result is not None
        # All three templates describe an AI/program — at least one of these terms appears
        assert any(word in result.lower() for word in ("shaggoth", "ai", "program", "software"))

    def test_what_are_you_matches_self_awareness(self):
        result = self.engine.respond("What are you?")
        assert result is not None

    def test_are_you_ai_matches(self):
        result = self.engine.respond("Are you an AI?")
        assert result is not None

    def test_where_do_you_run_matches(self):
        result = self.engine.respond("Where do you run?")
        assert result is not None
        assert "r510" in result.lower() or "Dell" in result

    def test_how_do_you_learn_matches(self):
        result = self.engine.respond("How do you learn?")
        assert result is not None

    def test_do_you_have_feelings_matches(self):
        result = self.engine.respond("Do you have feelings?")
        assert result is not None

    def test_can_you_captures(self):
        result = self.engine.respond("Can you juggle?")
        assert result is not None
        assert "juggle" in result

    def test_can_you_skips_knowledge_requests(self):
        assert self.engine.respond("Can you explain recursion?") is None
        assert self.engine.respond("Can you tell me about gravity?") is None
        assert self.engine.respond("Can you describe photosynthesis?") is None
        assert self.engine.respond("Can you help me with Python?") is None

    def test_because_captures(self):
        result = self.engine.respond("because gravity")
        assert result is not None

    def test_yes_matches(self):
        result = self.engine.respond("yes")
        assert result is not None

    def test_no_matches(self):
        result = self.engine.respond("no")
        assert result is not None

    def test_first_matching_rule_wins(self):
        # Rules are ordered; 'hello' should match greeting, not fall-through
        result = self.engine.respond("hello")
        assert result is not None

    def test_case_insensitive_matching(self):
        result_lower = self.engine.respond("who are you")
        result_upper = self.engine.respond("WHO ARE YOU")
        assert result_lower is not None
        assert result_upper is not None

    def test_fallback_returns_string(self):
        result = self.engine.fallback()
        assert isinstance(result, str)
        assert len(result) > 5

    def test_seed_produces_deterministic_output(self):
        eng1 = PatternEngine(seed=0)
        eng2 = PatternEngine(seed=0)
        # Greet-rule has multiple templates; seed should choose consistently
        for i in range(5):
            assert eng1.respond("hello") == eng2.respond("hello")

    def test_different_seeds_may_produce_different_output(self):
        # With enough samples at least one choice should differ between seeds
        outputs = set()
        for seed in range(20):
            eng = PatternEngine(seed=seed)
            out = eng.respond("hello")
            if out:
                outputs.add(out)
        # There are 3 greeting templates; different seeds should surface all
        assert len(outputs) > 1

    # -- New conversational pattern rules -----------------------------------

    def test_thank_you_matches(self):
        for text in ("thank you", "thanks", "thanks a lot", "thx", "ty"):
            assert self.engine.respond(text) is not None, text

    def test_sorry_matches(self):
        for text in ("sorry", "my bad", "I'm sorry"):
            assert self.engine.respond(text) is not None, text

    def test_farewell_matches(self):
        for text in ("bye", "goodbye", "see you later", "good night", "gotta go"):
            assert self.engine.respond(text) is not None, text

    def test_help_request_matches(self):
        for text in ("help", "help me", "what can you do"):
            assert self.engine.respond(text) is not None, text

    def test_whats_your_name_matches(self):
        result = self.engine.respond("what's your name")
        assert result is not None
        assert "shaggoth" in result.lower()

    def test_how_old_are_you_matches(self):
        assert self.engine.respond("how old are you") is not None

    def test_whats_up_matches(self):
        assert self.engine.respond("what's up") is not None

    def test_never_mind_matches(self):
        for text in ("never mind", "forget it", "nvm", "whatever", "idc"):
            assert self.engine.respond(text) is not None, text

    def test_reaction_matches(self):
        for text in ("that's cool", "no way", "for real", "damn", "oh wow"):
            assert self.engine.respond(text) is not None, text

    def test_wait_matches(self):
        for text in ("wait", "hold on", "one sec"):
            assert self.engine.respond(text) is not None, text

    def test_interjection_matches(self):
        for text in ("ugh", "sigh", "meh", "bruh", "hmm"):
            assert self.engine.respond(text) is not None, text

    def test_agreement_praise_reactions_match(self):
        for text in ("that was fun", "nice one", "good job", "well done",
                      "I agree", "fair enough", "good point", "my bad",
                      "you make me laugh"):
            assert self.engine.respond(text) is not None, text

    def test_i_need_you_to_does_not_match(self):
        result = self.engine.respond("I need you to tell me about Python")
        assert result is None

    def test_confusion_matches(self):
        for text in ("I don't know", "i have no idea", "no clue", "beats me",
                      "i'm not sure", "i'm confused"):
            assert self.engine.respond(text) is not None, text

    def test_joke_story_requests_match(self):
        for text in ("tell me a joke", "tell me a story", "make me laugh",
                      "tell me a fun fact"):
            assert self.engine.respond(text) is not None, text

    def test_insult_matches(self):
        for text in ("you suck", "you're stupid", "you're useless",
                      "you are terrible", "shut up"):
            assert self.engine.respond(text) is not None, text
