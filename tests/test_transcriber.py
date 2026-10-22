from whisper_shortcut.transcriber import clean_transcript


def test_clean_transcript_joins_nonempty_segments() -> None:
    assert clean_transcript([" Hello ", "", " world.  "]) == "Hello world."


def test_clean_transcript_handles_silence() -> None:
    assert clean_transcript([" ", "\n"]) == ""
