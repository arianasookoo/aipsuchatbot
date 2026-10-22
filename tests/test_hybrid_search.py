from hybrid_search import keyword_scores, terms


def test_terms_lowercases_and_drops_stop_words():
    assert terms("How can I SPONSOR the Capstone") == ["sponsor", "capstone"]


def test_terms_strips_plural_s_but_not_ss():
    assert terms("jobs class") == ["job", "class"]


def test_terms_turns_ies_into_y():
    assert terms("companies") == ["company"]


def test_terms_strips_ing_only_on_long_words():
    assert terms("engineering bring") == ["engineer", "bring"]


DOCS = ["Details here.", "Notes on capstone sponsorship.", "Lots and permits."]
METAS = [{"title": "Capstone Sponsorship"}, {"title": "Other"}, {"title": "Parking"}]


def test_keyword_scores_returns_one_float_per_document():
    scores = keyword_scores("capstone sponsorship", DOCS, METAS)
    assert len(scores) == 3
    assert all(isinstance(s, float) for s in scores)


def test_keyword_scores_title_match_outranks_body_match():
    scores = keyword_scores("capstone sponsorship", DOCS, METAS)
    assert scores[0] > scores[1] > 0


def test_keyword_scores_no_matching_terms_is_zero():
    assert keyword_scores("capstone sponsorship", DOCS, METAS)[2] == 0.0
