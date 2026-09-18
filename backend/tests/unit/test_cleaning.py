from vocab.adapters.nlp.cleaning import clean_sentence, is_truncated


def test_keeps_final_period_before_footnote_bracket():
    """El corchete se quita, el punto que lo precede no."""
    assert clean_sentence("Rates fell to 78 %.[") == "Rates fell to 78 %."
    assert not is_truncated(clean_sentence("Rates fell to 78 %.["))
