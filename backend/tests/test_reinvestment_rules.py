import pytest


def test_growth_phase_flag():
    from engines.capital_allocator import capital_allocator

    assert capital_allocator.is_growth_phase(2, 5) is True
    assert capital_allocator.is_growth_phase(5, 5) is False
    assert capital_allocator.is_growth_phase(0, 1) is True
    assert capital_allocator.is_growth_phase(0, 0) is False
    assert capital_allocator.is_growth_phase(-1, 5) is False
    assert capital_allocator.is_growth_phase(6, 5) is False
