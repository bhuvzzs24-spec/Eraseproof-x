from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CustomerData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=r"^[a-zA-Z0-9._+-]+@example\.invalid$")


class OrderData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    customer_id: UUID
    amount_cents: int = Field(gt=0)
    currency: Literal["USD", "INR", "EUR"]


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID = Field(default_factory=uuid4)
    version: Literal[1] = 1
    event_type: Literal["customer.created", "order.created"]
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: UUID
    customer_id: UUID
    data: CustomerData | OrderData

    @model_validator(mode="after")
    def consistent(self):
        expected = CustomerData if self.event_type == "customer.created" else OrderData
        if not isinstance(self.data, expected):
            raise ValueError("event type and data disagree")
        subject = self.data.id if isinstance(self.data, CustomerData) else self.data.customer_id
        if subject != self.customer_id:
            raise ValueError("customer identity mismatch")
        return self
