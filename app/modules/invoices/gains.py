"""Construction de la courbe de gains cumulés — fonctions pures, testées unitairement.

Le SVG est généré côté serveur (polyline), cohérent avec la stack Jinja/HTMX :
pas de lib JS de graphes pour une simple courbe croissante.
"""

from decimal import Decimal

SVG_WIDTH = 640
SVG_HEIGHT = 160
PADDING = 8


def cumulative_series(daily: list[tuple]) -> list[tuple]:
    """[(jour, montant_du_jour)] (chronologique) → [(jour, cumul)] — jamais décroissant."""
    total = Decimal("0")
    series = []
    for day, amount in daily:
        total += amount
        series.append((day, total))
    return series


def svg_polyline_points(
    series: list[tuple], width: int = SVG_WIDTH, height: int = SVG_HEIGHT
) -> str:
    """[(jour, cumul)] → attribut `points` d'une polyline SVG (x=temps, y=cumul).

    Un point unique est doublé pour rester visible (segment horizontal).
    """
    if not series:
        return ""
    if len(series) == 1:
        series = [series[0], series[0]]
    max_value = series[-1][1] or Decimal("1")
    inner_w, inner_h = width - 2 * PADDING, height - 2 * PADDING
    step = inner_w / (len(series) - 1)
    points = []
    for index, (_, value) in enumerate(series):
        x = PADDING + index * step
        y = PADDING + inner_h * (1 - float(value / max_value))
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)
