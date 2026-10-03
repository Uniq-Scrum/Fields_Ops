# Customer Request & Intake Validation Tests

This document describes the test cases created to ensure the `CustomerRequestPayload` schema accurately implements the required backend validation logic. It also provides instructions on how to execute these tests.

## Test Cases Mapped to Acceptance Criteria

### 1. Required request data is validated
**Test**: `test_missing_text_and_audio_rejected`
- **Description**: Ensures that the system strictly requires at least one form of input (`text_input` or `audio_url`). 
- **Behavior**: If both are missing, a `ValidationError` is raised preventing the data from entering the workflow.

### 2. Missing values are rejected
**Test**: `test_missing_text_and_audio_rejected`
- **Description**: Same as above, ensuring that payloads completely missing critical data are blocked.

### 3. Invalid values are rejected
**Test**: `test_blank_text_input_rejected`
- **Description**: Rejects text descriptions that contain only spaces (`"   "`).

**Test**: `test_invalid_audio_url_rejected`
- **Description**: Validates that if `audio_url` is provided, it must be a valid URL. If an invalid string (e.g., `"not-a-url"`) is sent, a `ValidationError` is triggered.

**Test**: `test_invalid_location_latitude_rejected` & `test_invalid_location_longitude_rejected`
- **Description**: Ensures that location coordinates are mathematically valid (latitude between -90 and 90, longitude between -180 and 180).

### 4. Validation errors return a structured response
*Note on Implementation*: By leveraging Pydantic, FastAPI intrinsically maps any `ValidationError` (like the ones tested above) into a structured `422 Unprocessable Entity` JSON response. The tests verify that Pydantic effectively intercepts and raises these structured errors upon validation failure.

### 5. Valid requests continue to processing
**Test**: `test_valid_text_request`
- **Description**: Sends a correctly formatted text request and verifies it is parsed correctly and allowed to proceed.

**Test**: `test_valid_audio_request`
- **Description**: Sends a correctly formatted audio URL request and verifies it passes validation.

**Test**: `test_missing_location_allowed`
- **Description**: Validates that location is truly optional; requests without location data but valid text/audio still successfully pass to processing.

---

## Customer Intake Request Validation Tests (Multi-Modal Workflow)

These tests ensure the `CustomerIntakeRequest` schema enforces strict validation rules, particularly around text input, across text and voice intake modalities.

### 1. Empty or Whitespace Requests are Rejected
**Test**: `test_empty_text_request_rejected`
- **Description**: Ensures that a text request with an empty string `""` is rejected.

**Test**: `test_whitespace_only_text_request_rejected`
- **Description**: Ensures that a text request containing only spaces, tabs, or newlines is rejected.

**Test**: `test_voice_request_with_whitespace_text_rejected`
- **Description**: Ensures that even for a voice request, if `request_text` is optionally provided, it cannot be a whitespace-only string.

### 2. Missing Request Text is Rejected (When Required)
**Test**: `test_missing_text_request_rejected`
- **Description**: Rejects a payload explicitly specifying `input_type="TEXT"` without providing `request_text`.

**Test**: `test_default_input_type_missing_text_rejected`
- **Description**: Rejects a payload with no `input_type` and no voice references, as it defaults to expecting a valid text request.

### 3. Valid Requests Proceed
**Test**: `test_valid_text_request`
- **Description**: Sends a correctly formatted text request and verifies it passes validation.

**Test**: `test_valid_voice_request`
- **Description**: Sends a correctly formatted voice request (with `input_type="VOICE"` and `audio_ref`) and verifies it passes.

**Test**: `test_missing_input_type_with_audio_ref_valid`
- **Description**: Confirms that providing an `audio_ref` without explicitly setting `input_type="VOICE"` is correctly inferred and validated as a voice request.

---

## Instructions: How to Run the Tests

To test the module and verify all rules are passing, you can run the provided unit tests via `pytest`.

### Step 1: Open your terminal
Ensure you are in the project root directory (`e:\FLIXFLEET_STRUCTURE`).

### Step 2: Activate the Virtual Environment
Activate the backend environment using PowerShell:
```powershell
.\env\Scripts\activate
```

### Step 3: Run the Tests
Execute the specific test files using `pytest`:

For Customer Request Payload tests:
```powershell
python -m pytest backend\tests\test_customer_request_validation.py -v
```

For Customer Intake Request tests:
```powershell
python -m pytest backend\tests\test_customer_intake_validation.py -v
```

### Expected Output
You should see output similar to the following, indicating that all 8 validation test cases have passed successfully:
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-8.3.4, pluggy-1.6.0
collected 8 items

backend\tests\test_customer_request_validation.py::test_valid_text_request PASSED
backend\tests\test_customer_request_validation.py::test_valid_audio_request PASSED
backend\tests\test_customer_request_validation.py::test_missing_text_and_audio_rejected PASSED
backend\tests\test_customer_request_validation.py::test_blank_text_input_rejected PASSED
backend\tests\test_customer_request_validation.py::test_invalid_audio_url_rejected PASSED
backend\tests\test_customer_request_validation.py::test_invalid_location_latitude_rejected PASSED
backend\tests\test_customer_request_validation.py::test_invalid_location_longitude_rejected PASSED
backend\tests\test_customer_request_validation.py::test_missing_location_allowed PASSED

============================== 8 passed in 1.00s ==============================
```

---

## Manual API Testing via Swagger UI

If you want to manually test the `CustomerIntakeRequest` validation logic using the FastAPI interactive documentation (`/docs`), you can run the server and use the following JSON payloads.

1. Start the development server:
   ```powershell
   cd backend
   uvicorn app.main:app --reload
   ```
2. Navigate to [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) in your browser.
3. Open the **`POST /api/v1/requests/intake`** endpoint and click **Try it out**.
4. Use the following payloads in the Request Body:

### ✅ Test Case A: Valid Text Request
**Expected Result**: `200 OK` (Validation passes, request proceeds).
```json
{
  "input_type": "TEXT",
  "request_text": "My kitchen sink is leaking continuously from the bottom pipe.",
  "customer_info": {
    "name": "John Doe",
    "phone": "555-1234"
  }
}
```

### ❌ Test Case B: Empty Text Request (Rejected)
**Expected Result**: `422 Unprocessable Entity` (Validation catches the empty string).
```json
{
  "input_type": "TEXT",
  "request_text": "",
  "customer_info": {}
}
```

### ❌ Test Case C: Whitespace-Only Text Request (Rejected)
**Expected Result**: `422 Unprocessable Entity`
```json
{
  "input_type": "TEXT",
  "request_text": "      \n   ",
  "customer_info": {}
}
```

### ❌ Test Case D: Missing Text Request (Rejected)
**Expected Result**: `422 Unprocessable Entity`
```json
{
  "input_type": "TEXT",
  "customer_info": {}
}
```

### ✅ Test Case E: Valid Voice Request
**Expected Result**: `200 OK` (Validation passes because voice inputs have different requirements).
```json
{
  "input_type": "VOICE",
  "audio_ref": "s3://my-bucket/recordings/audio123.mp3",
  "customer_info": {}
}
```

### ❌ Test Case F: Voice Request with Invalid Optional Text (Rejected)
**Expected Result**: `422 Unprocessable Entity`
```json
{
  "input_type": "VOICE",
  "audio_ref": "s3://my-bucket/recordings/audio123.mp3",
  "request_text": "    ",
  "customer_info": {}
}
```
