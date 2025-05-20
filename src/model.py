from abc import abstractmethod
import os
from typing import Optional
from enum import Enum
import uuid
from dyntastic import Dyntastic
from pydantic import BaseModel, Field, model_validator
from decimal import Decimal


class StrEnumMixin(str, Enum):
    def __str__(self):
        return self.value


class DynamoDbModelBase(Dyntastic):
    __table_region__ = os.environ.get("AWS_REGION")
    __table_host__ = os.environ.get("DYNAMO_ENDPOINT")
    __hash_key__ = "hash_key"
    __range_key__ = "range_key"

    @property
    @abstractmethod
    def __table_name__(self):  # override this on each implementing class
        pass

    hash_key: str = Field(default=None, title="DynamoDB Partition Key")
    range_key: str = Field(default=None, title="DynamoDB Sort Key")


class UserInfo(BaseModel):
    first_name: str
    last_name: str


class User(DynamoDbModelBase):
    __table_name__ = "User"
    __hash_key__ = "user_id"
    __range_key__ = None

    info: Optional[UserInfo]
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class Frequency(StrEnumMixin):
    DAILY = "DAILY"
    BI_MONTHLY = "BI-MONTHLY"


class CryptoType(StrEnumMixin):
    BTC = "BTC"
    ETH = "ETH"


class CurrencyType(StrEnumMixin):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    MXN = "MXN"


class RecurringOrder(DynamoDbModelBase):
    __table_name__ = "recurring-orders"
    __hash_key__ = "user_id"
    __range_key__ = "range_key"

    user_id: str
    crypto: CryptoType
    frequency: Frequency
    currency: CurrencyType
    amount: Decimal

    @model_validator(mode="before")
    def compute_composite_key(cls, values):
        """
        Dynamically compute and assign the DynamoDB sort key (`range_key`) by combining
        the crypto and frequency values into a single string (e.g., "BTC#DAILY").

        This pattern ensures that:
        - Each recurring order is uniquely identifiable for a specific (crypto, frequency) pair per user.
        - We can efficiently perform `get` or `safe_get` queries using the composite key without scanning.
        - We avoid storing a separate composite field in the database, relying instead on this dynamic assignment.

        This supports both business logic enforcement (one order per crypto-frequency per user)
        and efficient key-based operations in DynamoDB.
        """
        if (crypto := values.get("crypto")) and (frequency := values.get("frequency")):
            values["range_key"] = f"{crypto}#{frequency}"
        return values
