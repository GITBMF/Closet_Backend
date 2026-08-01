"""Exceptions personnalisées du module Showcasing."""
from fastapi import HTTPException, status


class SponsorNotFoundException(HTTPException):
    def __init__(self, sponsor_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le sponsor avec l'identifiant {sponsor_id} n'a pas été trouvé."
        )


class FeaturedSlotNotFoundException(HTTPException):
    def __init__(self, slot_id: int):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Le slot mis en avant N°{slot_id} n'a pas été trouvé."
        )


class InvalidSlotTypeException(HTTPException):
    def __init__(self, slot_type: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Le type de slot '{slot_type}' n'est pas valide."
        )