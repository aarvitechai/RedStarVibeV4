import type { components } from "../../../../../packages/api-types";

type S = components["schemas"];
export type Post = S["PostOut"];
export type PostPage = S["PostPage"];
export type Comment = S["CommentOut"];
export type Profile = S["ProfileOut"];
export type StoryGroup = S["StoryGroup"];
export type Conversation = S["ConversationOut"];
export type ChatMessage = S["MessageOut"];
