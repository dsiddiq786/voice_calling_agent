from app.speech import romanize_transcript, urdu_for_tts


def test_roman_urdu_is_prepared_for_pakistani_voice():
    spoken = urdu_for_tts(
        "Assalam-o-Alaikum, NomNosh se Fatima. Jee, aap kya order karna chahein ge?"
    )
    assert "السلام علیکم" in spoken
    assert "نوم نوش" in spoken
    assert "فاطمہ" in spoken
    assert "آپ کیا آرڈر کرنا چاہیں گے" in spoken


def test_urdu_stt_is_displayed_as_roman_urdu():
    shown = romanize_transcript("جی میں پیزا آرڈر کرنا چاہوں گا")
    assert shown == "jee main pizza order karna chahoon ga"
