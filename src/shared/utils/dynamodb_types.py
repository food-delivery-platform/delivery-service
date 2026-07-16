from decimal import Decimal


def floats_to_decimal(value):
    """boto3's DynamoDB resource API rejects native floats — recursively convert to Decimal."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: floats_to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [floats_to_decimal(v) for v in value]
    return value
