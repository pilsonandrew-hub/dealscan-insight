"""Vehicle make/model normalization and alias resolution."""

# Known acronyms/brands that must stay uppercase
_UPPERCASE_MAKES = {
    "BMW", "GMC", "VW", "RAM", "KIA", "MINI", "INFINITI", "LEXUS", "ACURA",
    "FIAT", "JAC", "GAC", "BYD", "FAW", "UAZ", "VAZ", "ZAZ", "SEAT",
}

# Known model acronyms that must stay uppercase
_UPPERCASE_MODELS = {
    "MDX", "RDX", "TLX", "ILX", "ZDX", "NSX", "TSX", "RSX",
    "CX5", "CX-5", "CX3", "CX-3", "CX9", "CX-9", "CX30", "CX-30",
    "RAV4", "CR-V", "CRV", "HR-V", "HRV", "BR-V",
    "F-150", "F150", "F-250", "F250", "F-350", "F350",
    "GLC", "GLE", "GLS", "AMG", "GLB", "GLK",
    "Q3", "Q5", "Q7", "Q8", "A3", "A4", "A5", "A6", "A7", "A8",
    "X1", "X2", "X3", "X4", "X5", "X6", "X7",
    "IS", "ES", "GS", "GX", "LX", "NX", "RX", "UX",
    "G35", "G37", "Q50", "Q60", "QX50", "QX60", "QX80",
}


def _normalize_make(make: str) -> str:
    """Normalize vehicle make, preserving known acronyms."""
    m = (make or "").strip()
    if not m:
        return m
    upper = m.upper()
    if upper in _UPPERCASE_MAKES:
        return upper
    return m.title()


def _normalize_model(model: str) -> str:
    """Normalize vehicle model, preserving known acronyms."""
    d = (model or "").strip()
    if not d:
        return d
    upper = d.upper()
    if upper in _UPPERCASE_MODELS or d.upper() in _UPPERCASE_MODELS:
        return upper
    return d.title()


def canonical(make: str, model: str) -> tuple[str, str]:
    """Normalize make and model to canonical forms."""
    m = _normalize_make(make)
    d = _normalize_model(model)
    # Known aliases
    if m == "Ford" and d.upper() in {"F150", "F-150", "F 150"}:
        d = "F-150"
    if m == "Chevrolet" and d.title() in {"Silverado", "Silverado 1500"}:
        d = "Silverado 1500"
    return m, d
