from uuid import uuid4
import httpx

suffix = uuid4().hex
response = httpx.post(
    "http://localhost:8000/v1/customers",
    timeout=5,
    json={"name": f"Synthetic Customer {suffix[:8]}", "email": f"{suffix}@example.invalid"},
)
response.raise_for_status()
print(response.text)
