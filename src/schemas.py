from typing import Annotated
from pydantic import BaseModel, BeforeValidator, Field
from .model import CryptoType, Frequency
from decimal import Decimal


def to_upper(v: str) -> str:
    return v.upper() if isinstance(v, str) else v


ValidatedCryptoType = Annotated[CryptoType, BeforeValidator(to_upper)]
ValidatedFrequencyType = Annotated[Frequency, BeforeValidator(to_upper)]
ValidatedAmountType = Annotated[
    Decimal,
    Field(gt=0, decimal_places=2),
]


class CreateOrderRequest(BaseModel):
    crypto: ValidatedCryptoType
    frequency: ValidatedFrequencyType
    amount: ValidatedAmountType


class OrderResponse(BaseModel):
    crypto: CryptoType
    frequency: Frequency
    amount: float
