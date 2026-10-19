"""Auslosung: jede Person beschenkt genau eine andere, unter Beachtung der Sperren."""
import random


class NoMatchingPossible(Exception):
    pass


def draw(people, forbidden, rng=None):
    """
    people:    Liste von Schlüsseln (z. B. E-Mail-Adressen)
    forbidden: Funktion (giver, receiver) -> True, wenn das Paar nicht erlaubt ist
    Liefert ein Dict giver -> receiver oder wirft NoMatchingPossible.
    """
    rng = rng or random.SystemRandom()
    if len(people) < 2:
        raise NoMatchingPossible("Es werden mindestens 2 Teilnehmer benötigt.")

    options = {g: [r for r in people if r != g and not forbidden(g, r)] for g in people}
    for g, opts in options.items():
        if not opts:
            raise NoMatchingPossible(f"Für {g} gibt es keinen erlaubten Wichtelpartner.")

    # Am stärksten eingeschränkte Schenker zuerst, Kandidaten zufällig gemischt
    givers = sorted(people, key=lambda g: (len(options[g]), rng.random()))
    result, taken = {}, set()

    def backtrack(i):
        if i == len(givers):
            return True
        g = givers[i]
        candidates = [r for r in options[g] if r not in taken]
        rng.shuffle(candidates)
        for r in candidates:
            result[g] = r
            taken.add(r)
            if backtrack(i + 1):
                return True
            taken.discard(r)
            del result[g]
        return False

    if not backtrack(0):
        raise NoMatchingPossible(
            "Mit den aktuellen Haushalts- und Vorjahressperren ist keine Auslosung möglich.")
    return result
