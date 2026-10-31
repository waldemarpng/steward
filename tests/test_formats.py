import pytest

from steward.formats import parse_env, to_env


def test_parse_reads_what_to_env_writes() -> None:
    values = {
        "PLAIN": "abc-1.2/x",
        "SPACED": "a b c",
        "QUOTE": 'it\'s "here"',
        "DOLLAR": "pa$$word's",
        "LINES": "one\ntwo\r\nthree",
        "SLASH": "back\\slash'",
        "EMPTY": "",
    }
    assert parse_env(to_env(values)) == values


def test_parse_skips_comments_blank_lines_and_export() -> None:
    source = "\ufeff# header\n\nexport A=1\nB=2 # trailing note\nC='#kept'\n"
    assert parse_env(source) == {"A": "1", "B": "2", "C": "#kept"}


def test_parse_keeps_equals_in_value_and_last_line_wins() -> None:
    assert parse_env("URL=a=b\nURL=c=d") == {"URL": "c=d"}


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("NOEQUALS", "line 1: expected KEY=value"),
        ("A=1\nMY KEY=2", 'line 2: invalid name "MY KEY"'),
        ("1A=x", 'invalid name "1A"'),
        ("A='open", "line 1: unclosed '"),
        ('A="x" tail', 'line 1: text after the closing "'),
        ("", "no KEY=value lines"),
    ],
)
def test_parse_rejects_bad_input(source: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_env(source)
