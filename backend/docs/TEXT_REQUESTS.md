# Text Repair Requests

## Submit a request

`POST /api/v1/service-requests` accepts an authenticated customer repair
description, passes the normalized text and authenticated customer ID to the
intake flow, then saves it in `service_requests`.

Request:

```json
{
  "request_text": "My kitchen sink is leaking under the cabinet."
}
```

`request_text` is required, trimmed before intake, must contain at least one
non-whitespace character, and is limited to 2,000 characters. Only callers
with the `CUSTOMER` role may submit requests.

Success (`201 Created`):

```json
{
  "request_id": "2a15bf9e-5d99-4ab1-8d15-66f684655210",
  "status": "received"
}
```

The stored row contains the request UUID, customer UUID, normalized text,
`RECEIVED` status, and creation timestamp. Deleting a customer cascades to
their requests. Validation failures return `422 Unprocessable Entity`; missing
or invalid authentication returns `401 Unauthorized`, and other roles receive
`403 Forbidden`. Classification and dispatch are not yet implemented.