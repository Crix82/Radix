from app.services.search.fusion import rrf_fuse
from app.services.search.snippet import make_snippet


def test_rrf_rewards_agreement_across_lists() -> None:
    dense = [10, 20, 30]
    fts = [20, 40, 10]
    fused = dict(rrf_fuse([dense, fts]))
    # 20 is rank 2 in dense and rank 1 in fts; 10 is rank 1 and rank 3 -> both strong,
    # but every id present in both must outrank ids present in only one.
    assert fused[20] > fused[40]
    assert fused[10] > fused[30]


def test_rrf_orders_by_score() -> None:
    fused = rrf_fuse([[1, 2, 3], [1, 2, 3]])
    ids = [i for i, _ in fused]
    assert ids == [1, 2, 3]


def test_rrf_empty() -> None:
    assert rrf_fuse([[], []]) == []


def test_rrf_k_dampens_rank_gaps() -> None:
    # With k=60 the gap between rank 1 and rank 2 is small (1/61 vs 1/62).
    fused = dict(rrf_fuse([[1, 2]]))
    assert abs(fused[1] - fused[2]) < 0.001


def test_snippet_highlights_query_terms() -> None:
    text = "La coppia di serraggio della testata e di 85 Nm come da specifica."
    html = make_snippet(text, "coppia di serraggio testata")
    assert "<b>coppia</b>" in html
    assert "<b>serraggio</b>" in html
    assert "<b>testata</b>" in html


def test_snippet_escapes_html() -> None:
    html = make_snippet("valore <x> & 'quote' pericoloso", "valore")
    assert "&lt;x&gt;" in html and "&amp;" in html
    assert "<b>valore</b>" in html


def test_snippet_windows_around_first_match() -> None:
    text = "intro " * 60 + "TARGET parola chiave " + "coda " * 60
    html = make_snippet(text, "TARGET", max_len=120)
    assert "<b>TARGET</b>" in html
    assert html.startswith("…") and html.endswith("…")
    assert len(html) < 200


def test_snippet_ignore_short_terms() -> None:
    html = make_snippet("a e i o u parola", "a e parola")
    assert "<b>parola</b>" in html
    assert "<b>a</b>" not in html  # 1-char terms dropped
