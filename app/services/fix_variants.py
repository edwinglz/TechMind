"""Fix variants: the different ways a known issue gets fixed.

For now this holds the step normalization used to group identical fixes when
importing ticket history. The success-rate and recommended-fix logic arrives
in Phase 5.
"""

import re


def normalize_steps(steps: list[str]) -> tuple[str, ...]:
    """Make two step lists comparable despite case, spacing, and trailing periods.

    Imported history writes the same fix in the same words, so an exact match
    after this cleanup is enough to group it. Fixes described in free text by a
    technician are matched by the AI instead (Phase 5).
    """
    return tuple(re.sub(r"\s+", " ", s).strip().rstrip(".").lower() for s in steps if s.strip())
