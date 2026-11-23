# Provider protocol sources

The native adapters are independently implemented Rust. The retained Python 2.5.5 contract is commit 070fa25b07692c90c56a6b00a9a969ff2abb7804, specifically reverie/agent/agent.py, reverie/custom_providers.py and reverie/gemini.py under the repository MIT license. The implementation does not invoke the Python SDKs.

Primary documentation consulted on 2026-11-23:

- [OpenAI function calling and streaming tool arguments](https://developers.openai.com/api/docs/guides/function-calling): native output items, call IDs, complete argument events and tool outputs.
- [Anthropic message streaming](https://platform.claude.com/docs/en/build-with-claude/streaming): content block lifecycle, text, thinking, signatures and the final message marker.
- [Google generateContent REST reference](https://aistudio.google.com/api-reference/generate-content): native HTTP methods, JSON Schema declarations, parts and generation completion.
- [Google function calling](https://ai.google.dev/gemini-api/docs/function-calling) and [thought signatures](https://ai.google.dev/gemini-api/docs/thought-signatures): preserve the function call and its original signed part. The documentation redirects to the current AI Studio documentation; this adapter retains the existing generateContent contract.

Local HTTP fixtures exercise wire behavior and actual native workspace tools. Their opaque test signatures are not cryptographic verification or evidence of compatibility with a live provider. Live services, account authorization, complete catalogs and model-specific options remain separately recorded in the migration and verification documents.
