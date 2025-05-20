from . import order_service
from .order_service import DuplicateOrderError, OrderCreationError, OrderLookupError
from fastapi import FastAPI, HTTPException, status, Depends, Path
from .model import User
from .schemas import CreateOrderRequest, OrderResponse
from typing import List

app = FastAPI(
    title="Investifi Backend Coding Challenge",
)


def get_existing_user_or_404(user_id: str = Path(...)) -> User:
    if not (user := User.safe_get(user_id)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )

    return user


@app.post(
    "/users/{user_id}/recurring-orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    user_id: str = Path(...),
    request: CreateOrderRequest = ...,
    user: User = Depends(get_existing_user_or_404),
):
    try:
        order = order_service.create_order(user.user_id, request)
        return OrderResponse(**order.model_dump())
    except DuplicateOrderError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except (OrderCreationError, OrderLookupError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@app.get("/users/{user_id}/recurring-orders", response_model=List[OrderResponse])
def get_user_orders(
    user_id: str = Path(...), user: User = Depends(get_existing_user_or_404)
):
    try:
        orders = order_service.get_orders(user.user_id)
        return [OrderResponse(**order.model_dump()) for order in orders]
    except OrderLookupError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
