import { ApiFailure } from "../api/client";

export type GuidanceActionKind = "reenroll" | "refetch" | "fleet" | "reissue";

export interface GuidanceAction {
  label: string;
  to?: string;
  kind: GuidanceActionKind;
}

export interface ErrorGuidance {
  title: string;
  detail: string;
  code?: string;
  action?: GuidanceAction;
  surface: "browser" | "operation" | "agent";
  retryable: boolean;
}

function sanitizeMessage(msg: string): string {
  // Strip token-shaped or secret strings
  return msg.replace(/(?:bstrp|agt|bearer|session)[-_a-zA-Z0-9]{8,}/gi, "[REDACTED]");
}

export function guidanceFor(failure: unknown): ErrorGuidance {
  let kind: "http" | "network" | undefined;
  let status: number | undefined;
  let code: string | undefined;
  let rawMessage = "An unexpected error occurred.";

  if (failure instanceof ApiFailure) {
    kind = failure.kind;
    status = failure.status;
    code = failure.code;
    rawMessage = failure.message;
  } else if (failure instanceof Error) {
    rawMessage = failure.message;
  } else if (typeof failure === "string") {
    rawMessage = failure;
  }

  const safeMessage = sanitizeMessage(rawMessage);

  if (kind === "network") {
    return {
      title: "Cannot reach NimbusOps server",
      detail: "Cannot reach the API. Check service, URL, or proxy connection.",
      surface: "browser",
      retryable: true,
      action: {
        label: "Retry connection",
        kind: "refetch",
      },
    };
  }

  switch (code) {
    case "HOST_REVOKED":
      return {
        title: "Host credential revoked",
        detail: "This host's credential is revoked. Re-enroll to reconnect.",
        code: "HOST_REVOKED",
        surface: "browser",
        retryable: false,
        action: {
          label: "Re-enroll host",
          kind: "reenroll",
        },
      };

    case "HOST_NOT_FOUND":
      return {
        title: "Host not found",
        detail: "This host no longer exists.",
        code: "HOST_NOT_FOUND",
        surface: "browser",
        retryable: false,
        action: {
          label: "Return to fleet",
          to: "/servers",
          kind: "fleet",
        },
      };

    case "BOOTSTRAP_TOKEN_EXPIRED":
    case "BOOTSTRAP_TOKEN_CONSUMED":
    case "BOOTSTRAP_TOKEN_INVALID":
      return {
        title: "Bootstrap token unusable",
        detail: "This enrollment token is no longer usable.",
        code,
        surface: "browser",
        retryable: false,
        action: {
          label: "Issue a new token",
          kind: "reissue",
        },
      };

    case "BOOTSTRAP_TOKEN_ACTIVE":
      return {
        title: "Active token already exists",
        detail: "Another enrollment token is still active.",
        code: "BOOTSTRAP_TOKEN_ACTIVE",
        surface: "browser",
        retryable: false,
        action: {
          label: "Revoke and reissue",
          kind: "reissue",
        },
      };

    case "BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH":
      return {
        title: "Hostname mismatch",
        detail: "The token was issued for a different hostname.",
        code: "BOOTSTRAP_TOKEN_HOSTNAME_MISMATCH",
        surface: "browser",
        retryable: false,
        action: {
          label: "Reissue for correct hostname",
          kind: "reissue",
        },
      };

    case "HOSTNAME_TAKEN":
      return {
        title: "Hostname already registered",
        detail: "That hostname is already enrolled.",
        code: "HOSTNAME_TAKEN",
        surface: "browser",
        retryable: false,
        action: {
          label: "Re-enroll host",
          kind: "reenroll",
        },
      };

    case "OPERATOR_AUTH_REQUIRED":
      return {
        title: "Authentication required",
        detail: "Your session expired.",
        code: "OPERATOR_AUTH_REQUIRED",
        surface: "browser",
        retryable: false,
        action: {
          label: "Sign in",
          to: "/login",
          kind: "fleet",
        },
      };

    case "OPERATOR_FORBIDDEN":
      return {
        title: "Permission denied",
        detail: "Your role cannot perform this action.",
        code: "OPERATOR_FORBIDDEN",
        surface: "browser",
        retryable: false,
      };

    case "RATE_LIMITED":
      return {
        title: "Too many requests",
        detail: "Too many requests. Retry shortly.",
        code: "RATE_LIMITED",
        surface: "browser",
        retryable: true,
        action: {
          label: "Retry",
          kind: "refetch",
        },
      };

    case "DOCKER_NOT_AUTHORIZED":
      return {
        title: "Docker execution not authorized",
        detail: "Docker execution is disabled for this host.",
        code: "DOCKER_NOT_AUTHORIZED",
        surface: "operation",
        retryable: false,
      };

    case "DOCKER_UNAVAILABLE":
    case "DOCKER_FAILURE":
      return {
        title: "Docker unavailable",
        detail: "The host could not reach Docker.",
        code,
        surface: "operation",
        retryable: true,
        action: {
          label: "Retry",
          kind: "refetch",
        },
      };

    case "AGENT_UNREACHABLE":
    case "TIMEOUT":
      return {
        title: "Agent unreachable",
        detail: "The agent did not respond in time.",
        code,
        surface: "operation",
        retryable: true,
        action: {
          label: "Retry",
          kind: "refetch",
        },
      };

    case "FORBIDDEN_HOST":
    case "SIMULATED_HOST_REJECTED":
      return {
        title: "Invalid host identifier",
        detail: "This identifier is not a real host.",
        code,
        surface: "browser",
        retryable: false,
      };

    default: {
      const is5xx = status !== undefined && status >= 500 && status < 600;
      return {
        title: "Operation failed",
        detail: safeMessage,
        code,
        surface: "operation",
        retryable: is5xx,
        action: is5xx
          ? {
              label: "Retry",
              kind: "refetch",
            }
          : undefined,
      };
    }
  }
}
