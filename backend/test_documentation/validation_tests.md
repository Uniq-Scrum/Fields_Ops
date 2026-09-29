# Customer Request Payload Validation Tests

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
Execute the specific test file using `pytest`:
```powershell
python -m pytest backend\tests\test_customer_request_validation.py -v
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
