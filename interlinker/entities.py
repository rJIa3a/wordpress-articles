"""Conservative disambiguation of a city name inside another named entity."""
import re

def noncity_name(text,start):
    before=text[max(0,start-70):start]
    # Immediate type + at most two capitalized qualifiers: реки Лесной Воронеж.
    return bool(re.search(r'\b(?:река|реки|реке|реку|рекой|озеро|озера|озере|улица|улицы|улице|улицу|станция|станции|станцию)\s+(?:[А-ЯЁ][а-яё-]+\s+){0,2}$',before))
