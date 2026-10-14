export type CreateServiceRequestInput = {
  user_prompt: string;
};

export type CreateServiceRequestResponse = {
  job_id: string;
  message: string;
  status: string;
};

function getApiErrorMessage(body: unknown): string | null {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return null;
  }

  const detail = body.detail;
  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "object" && item !== null && "msg" in item && typeof item.msg === "string") {
          return item.msg;
        }
        return null;
      })
      .filter((message): message is string => message !== null);

    return messages.length > 0 ? messages.join(" ") : null;
  }

  return null;
}

function isCreateServiceRequestResponse(value: unknown): value is CreateServiceRequestResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "job_id" in value &&
    typeof value.job_id === "string" &&
    "message" in value &&
    typeof value.message === "string" &&
    "status" in value &&
    typeof value.status === "string"
  );
}

export async function createServiceRequest(
  payload: CreateServiceRequestInput,
): Promise<CreateServiceRequestResponse> {
  const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

  try {
    const response = await fetch(`${apiBaseUrl}/api/service-requests`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    let responseBody: unknown;
    try {
      responseBody = await response.json();
    } catch {
      throw new Error("The service request API returned an invalid response.");
    }

    if (!response.ok) {
      const apiMessage = getApiErrorMessage(responseBody);
      throw new Error(apiMessage ?? `Request failed with status ${response.status}.`);
    }

    if (!isCreateServiceRequestResponse(responseBody)) {
      throw new Error("The service request API returned an unexpected response.");
    }

    return responseBody;
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(
        "Unable to reach the service request API. Please check your connection and try again.",
      );
    }

    throw error;
  }
}
