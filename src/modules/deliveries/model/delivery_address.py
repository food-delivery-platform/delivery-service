from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class DeliveryAddress(BaseModel):
    """Used both internally (snake_case, e.g. DynamoDB storage via model_dump()) and embedded in
    HTTP responses (camelCase via model_dump(by_alias=True)) — alias_generator only kicks in
    when by_alias is explicitly requested, so both call sites stay correct."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    lat: float
    lng: float
    street: str | None = None
    city: str | None = None
    address_id: str | None = None
