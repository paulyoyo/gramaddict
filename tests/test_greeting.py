from GramAddict.core.interaction import build_greeting

LISTS = {
    "greetings": ["Hola {name}!", "Holi {name}!"],
    "source-context": ["Vi que sigues a {source} 🎶", "Te vi por {source} 🎧"],
    "mix-question": ["Saqué un mix nuevo, te lo paso?", "Tengo un mix nuevito, quieres oírlo?"],
}


def test_single_strings_still_work():
    config = {
        "greetings": ["Hola {name}!"],
        "source-context": "Vi que sigues a {source} 🎶",
        "mix-question": "Acabo de sacar un nuevo mix, quieres escucharlo?",
    }
    assert (
        build_greeting(config, "Ana", "club")
        == "Hola Ana! Vi que sigues a @club 🎶 Acabo de sacar un nuevo mix, quieres escucharlo?"
    )


def test_each_part_is_picked_from_its_list():
    seen = {build_greeting(LISTS, "Ana", "@club") for _ in range(300)}
    assert len(seen) == 8  # 2 openers x 2 source lines x 2 questions
    for text in seen:
        assert text.startswith(("Hola Ana!", "Holi Ana!"))
        assert "@club" in text


def test_no_source_line_without_a_source():
    for _ in range(20):
        assert "@" not in build_greeting(LISTS, "Ana", None)


def test_empty_name_is_tidied():
    assert build_greeting({"greetings": ["Hola {name}!"], "mix-question": "x?"}, "", None) == "Hola! x?"
