/** Aliases over the generated OpenAPI types (@rsv/api-types). Run `make types` after a backend schema change. */
import type { components } from "../../../../../packages/api-types";

export type Me = components["schemas"]["MeOut"];
export type SessionInfo = components["schemas"]["SessionOut"];
