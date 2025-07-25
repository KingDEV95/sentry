from __future__ import annotations

import math
from abc import ABC, abstractmethod


def nice_int(x: float) -> int:
    """
    Round away from zero to the nearest "nice" number.
    """

    if x == 0:
        return 0

    sign = 1 if x > 0 else -1
    x = abs(x)

    if x < 10:
        rounded = 1
        steps = [1, 2, 5, 10]
    elif x < 100:
        rounded = 1
        steps = [10, 20, 25, 50, 100]
    else:
        exp = int(math.log10(x))
        rounded = 10 ** (exp - 2)
        steps = [100, 120, 200, 250, 500, 750, 1000]

    nice_frac = steps[-1]
    frac = x / rounded
    for step in steps:
        if frac <= step:
            nice_frac = step
            break

    return sign * nice_frac * rounded


class MovingAverage(ABC):
    @abstractmethod
    def update(self, n: int, avg: float, value: float) -> float:
        raise NotImplementedError


class ExponentialMovingAverage(MovingAverage):
    def __init__(self, weight: float):
        super().__init__()
        assert 0 < weight and weight < 1
        self.weight = weight

    def update(self, n: int, avg: float, value: float) -> float:
        if n == 0:
            return value
        return value * self.weight + avg * (1 - self.weight)
