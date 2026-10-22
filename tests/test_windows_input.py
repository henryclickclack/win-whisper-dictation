from whisper_shortcut import windows_input
from whisper_shortcut.windows_input import TextInserter


def test_paste_last_recopies_retained_transcript(monkeypatch) -> None:
    copied: list[str] = []
    inserter = TextInserter.__new__(TextInserter)
    inserter._last_transcript = "retained words"
    monkeypatch.setattr(windows_input.pyperclip, "copy", copied.append)
    monkeypatch.setattr(inserter, "_send_paste", lambda: True)

    assert inserter.paste_last()
    assert copied == ["retained words"]


def test_paste_last_does_nothing_without_transcript(monkeypatch) -> None:
    copied: list[str] = []
    inserter = TextInserter.__new__(TextInserter)
    inserter._last_transcript = ""
    monkeypatch.setattr(windows_input.pyperclip, "copy", copied.append)

    assert not inserter.paste_last()
    assert copied == []
