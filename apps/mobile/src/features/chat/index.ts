// Chat feature (ARCHITECTURE §3 features/chat; PRODUCT_SPEC S9; API_CONTRACT §3.7).

export { assistantLines, ChatScreen, type ChatScreenProps, emergencyHref } from './ChatScreen';
export {
  analysisContext,
  buildChatRequest,
  compactOriginalText,
  DEFAULT_MAX_HISTORY,
  DEFAULT_MAX_QUESTION,
  historyForRequest,
  MAX_CONTEXT_CHARS,
} from './context';
export { CHAT_UNAVAILABLE_KEY, referKey, referShowsHelp, refusalKey, starterQuestions } from './refusalTemplates';
export {
  chatAvailable,
  type ChatTurn,
  isChatOffError,
  turnsToMessages,
  useChat,
  useChatHistory,
  type UseChat,
  type UseChatOptions,
} from './useChat';
