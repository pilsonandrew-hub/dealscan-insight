"""Vehicle make/model normalization and alias resolution."""


def canonical(make: str, model: str) -> tuple[str, str]:
    """Normalize make and model to canonical forms."""
    m = (make or "").strip().title()
    d = (model or "").strip().title()
    # Known aliases
    if m == "Ford" and d in {"F150", "F-150", "F 150"}:
        d = "F-150"
    if m == "Chevrolet" and d in {"Silverado", "Silverado 1500"}:
        d = "Silverado 1500"
    return m, d
