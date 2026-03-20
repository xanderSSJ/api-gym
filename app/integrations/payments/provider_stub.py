from __future__ import annotations


def create_checkout_reference(membership_id: str) -> str:
    return f"checkout_{membership_id}"
