"""Shared rules for the human-playable Simple Recommendation strategies."""

from typing import MutableMapping


def replace_current_recommendation(
    recommendations: MutableMapping[int, int],
    seat: int,
    code: int,
    *,
    minimum_code: int,
    maximum_code: int,
) -> None:
    """Keep at most one current actionable recommendation for ``seat``.

    A newly decoded unused code clears the previous recommendation. This is the
    shared single-recommendation model; it deliberately has no queue or backlog.
    """
    if minimum_code <= code <= maximum_code:
        recommendations[seat] = code
    else:
        recommendations.pop(seat, None)


def allows_recommended_play(plays_since_hint: int, errors: int) -> bool:
    """Return whether a decoded play recommendation is still safe to follow.

    The same rule is used at 3p, 4p, and 5p: act immediately, or after exactly
    one intervening team play while fewer than two life tokens have been lost.
    """
    if plays_since_hint == 0:
        return True
    return plays_since_hint == 1 and errors < 2


def is_shared_strong_hint(new_plays: int, new_discards: int, saves: int) -> bool:
    """Committed strong-hint rule shared by the 3p and 4p Simple bots."""
    return new_plays >= 2 or new_discards >= 1 or saves >= 1


def is_positive_hint(total_changes: int) -> bool:
    """A lower-tier hint must create at least one recommendation change."""
    return total_changes >= 1
