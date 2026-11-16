/** Aliases over the generated OpenAPI types (@rsv/api-types). Run `make types` after a backend schema change. */
import type { components } from "../../../../../packages/api-types";

type S = components["schemas"];

export type Me = S["MeOut"];
export type SessionInfo = S["SessionOut"];
export type BusinessPublic = S["BusinessPublic"];
export type BusinessOwnerView = S["BusinessOwnerView"];
export type Service = S["ServiceOut"];
export type Hours = S["HoursOut"];
export type SlotsResponse = S["SlotsOut"];
export type Booking = S["BookingOut"];
export type BookingPage = S["BookingPage"];
export type ReviewPage = S["ReviewPage"];
export type Review = S["ReviewOut"];
export type NotificationPage = S["NotificationPage"];
export type NearbyItem = S["NearbyItem"];
