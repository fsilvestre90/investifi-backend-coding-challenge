from typing import List

from .model import CurrencyType, RecurringOrder
from .schemas import CreateOrderRequest


class DuplicateOrderError(Exception):
    pass


class OrderCreationError(Exception):
    pass


class OrderLookupError(Exception):
    pass


def create_order(user_id: str, request: CreateOrderRequest) -> RecurringOrder:
    composite_key = f"{request.crypto}#{request.frequency}"

    try:
        existing = RecurringOrder.safe_get(hash_key=user_id, range_key=composite_key)
    except Exception as e:
        raise OrderLookupError(f"Failed to check existing order: {str(e)}")

    if existing:
        raise DuplicateOrderError(
            f"Recurring order already exists for user '{user_id}' with crypto '{request.crypto}' and frequency '{request.frequency}'."
        )

    try:
        order = RecurringOrder(
            user_id=user_id,
            crypto=request.crypto,
            frequency=request.frequency,
            currency=CurrencyType.USD,
            amount=request.amount,
        )
        order.save()
        return order
    except Exception as e:
        raise OrderCreationError(f"Failed to create recurring order: {str(e)}")


def get_orders(user_id: str) -> List[RecurringOrder]:
    """
    Retrieve all recurring orders for a given user.

    Args:
        user_id (str): The user_id whose orders should be retrieved.

    Returns:
        List[RecurringOrder]: A list of the user's recurring orders.
    """
    try:
        return list(RecurringOrder.query(user_id))
    except Exception as e:
        raise OrderLookupError(
            f"Failed to retrieve orders for user '{user_id}': {str(e)}"
        )
