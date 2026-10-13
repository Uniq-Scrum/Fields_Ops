export type CreateServiceRequestInput = {
  user_prompt: string;
};

export type CreateServiceRequestResponse = {
  job_id: string;
  message?: string;
  status?: string;
};

export async function createServiceRequest(
  payload: CreateServiceRequestInput,
): Promise<CreateServiceRequestResponse> {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${apiBaseUrl}/api/service-requests`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      throw new Error(
        errorBody?.detail ??
          errorBody?.message ??
          `Request failed with status ${response.status}.`,
      );
    }

    return (await response.json()) as CreateServiceRequestResponse;
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(
        "Unable to reach the service request API. Please make sure the backend is running.",
      );
    }

    throw error;
  }
}
