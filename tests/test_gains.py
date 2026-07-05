"""Tests du cumul de gains (fonctions pures de gains.py).

L'idempotence du backfill et la non-régression du cumul après rejet sont des
comportements base de données (UNIQUE + ON CONFLICT DO NOTHING) prouvés en réel
dans le protocole de la slice — ici on teste la construction de la courbe.
"""

from datetime import date
from decimal import Decimal

from app.modules.invoices import gains


def test_serie_cumulative_ne_redescend_jamais():
    daily = [
        (date(2026, 7, 1), Decimal("52")),
        (date(2026, 7, 3), Decimal("26")),
        (date(2026, 7, 6), Decimal("78")),
    ]
    series = gains.cumulative_series(daily)
    assert [value for _, value in series] == [Decimal("52"), Decimal("78"), Decimal("156")]
    assert all(series[i][1] <= series[i + 1][1] for i in range(len(series) - 1))


def test_serie_vide():
    assert gains.cumulative_series([]) == []
    assert gains.svg_polyline_points([]) == ""


def test_points_svg_croissent_en_x_et_descendent_en_y():
    # y SVG décroît quand la valeur monte (origine en haut à gauche)
    series = gains.cumulative_series([(date(2026, 7, d), Decimal("26")) for d in (1, 2, 3)])
    points = [tuple(map(float, p.split(","))) for p in gains.svg_polyline_points(series).split()]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    assert xs == sorted(xs) and xs[0] < xs[-1]
    assert ys == sorted(ys, reverse=True) and ys[0] > ys[-1]
    assert all(0 <= x <= gains.SVG_WIDTH and 0 <= y <= gains.SVG_HEIGHT for x, y in points)


def test_point_unique_reste_visible():
    series = gains.cumulative_series([(date(2026, 7, 6), Decimal("26"))])
    points = gains.svg_polyline_points(series).split()
    assert len(points) == 2  # doublé → segment horizontal visible
