import answer
from answer import build_prompt, keep_cited, render


def page(title, url, keyword_rank=1, vector_rank=1):
    return {"title": title, "sources": [{"url": url}], "text": f"About {title}.",
            "keyword_rank": keyword_rank, "vector_rank": vector_rank}


EVIDENCE = [page("Sponsor a Project", "https://x.psu.edu/sponsor"),
            page("Post a Job", "https://x.psu.edu/jobs")]


def ask(reply, evidence=EVIDENCE):
    return answer.answer("q", llm=lambda messages: reply, retriever=lambda q, db, k: evidence)


def test_keep_cited_keeps_valid_citations():
    assert keep_cited("Sponsor here [1]. Post jobs there [2][1].", 2) == "Sponsor here [1]. Post jobs there [2][1]."


def test_keep_cited_drops_uncited_sentence():
    assert keep_cited("Sponsor here [1]. I think so.", 2) == "Sponsor here [1]."


def test_keep_cited_drops_out_of_range_citation():
    assert keep_cited("Sponsor here [1]. Made up [3]. Mixed [1][3].", 2) == "Sponsor here [1]."


def test_keep_cited_splits_after_bracket_without_period():
    assert keep_cited("Sponsor here [1] I think so.", 2) == "Sponsor here [1]"


def test_keep_cited_empty_string():
    assert keep_cited("", 2) == ""


def test_build_prompt_numbers_evidence_from_one():
    prompt = build_prompt("How do I sponsor?", EVIDENCE)
    assert "[1] Sponsor a Project\nURL: https://x.psu.edu/sponsor\nAbout Sponsor a Project." in prompt
    assert "[2] Post a Job\nURL: https://x.psu.edu/jobs\nAbout Post a Job." in prompt
    assert "[0]" not in prompt


def test_build_prompt_ends_with_question():
    assert build_prompt("How do I sponsor?", EVIDENCE).endswith("Question: How do I sponsor?")


def test_answer_answerable_reply():
    out = ask("ANSWERABLE\nPost jobs there [2]. Sponsor here [1].")
    assert out["answer"] == "Post jobs there [2]. Sponsor here [1]."
    assert out["refused"] is False
    # citations come back sorted by number, not in order of first use
    assert [c["n"] for c in out["citations"]] == [1, 2]
    assert out["citations"][0]["url"] == "https://x.psu.edu/sponsor"


def test_answer_refusal_falls_back_to_top_evidence():
    out = ask(answer.REFUSAL, [page("Sponsor a Project", "https://x.psu.edu/sponsor", 3, 3)])
    assert out["refused"] is True
    assert out["answer"] == ""
    assert out["fallback"]["url"] == "https://x.psu.edu/sponsor"


def test_answer_refusal_falls_back_to_contact_page_when_vector_rank_is_weak():
    out = ask(answer.REFUSAL, [page("Sponsor a Project", "https://x.psu.edu/sponsor", 1, 4)])
    assert out["refused"] is True
    assert out["fallback"]["url"].endswith("/connect.aspx")


def test_answer_all_citations_out_of_range_is_refused():
    out = ask("ANSWERABLE\nMade up [7]. Also made up [9].")
    assert out["refused"] is True
    assert out["answer"] == ""


def test_render_refused_shows_fallback_url():
    text = render(ask(answer.REFUSAL))
    assert "https://x.psu.edu/sponsor" in text


def test_render_answered_lists_sources():
    text = render(ask("ANSWERABLE\nSponsor here [1]. Post jobs there [2]."))
    assert text.splitlines()[2] == "Sources:"
    assert "[1] Sponsor a Project\nhttps://x.psu.edu/sponsor" in text
    assert "[2] Post a Job\nhttps://x.psu.edu/jobs" in text


def test_keep_cited_does_not_split_on_abbreviations():
    assert keep_cited("Contact Dr. Jane Smith at the Learning Factory [1].", 2) == "Contact Dr. Jane Smith at the Learning Factory [1]."
    assert keep_cited("Ph.D. students may apply [2]. Unsupported claim here.", 2) == "Ph.D. students may apply [2]."
