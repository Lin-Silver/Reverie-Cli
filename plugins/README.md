# Plugins Source Tree

This directory is the plugin source workspace for Reverie CLI, not the in-process plugin framework.

Directory roles:

- `reverie/plugin/`
  Main-process plugin protocol, discovery, dynamic tool wiring, and prompt integration.
- `plugins/<plugin-id>/`
  Source code for each plugin wrapper or runtime bridge.
- `plugins/_sdk/`
  Small shared helper files used by plugin source trees.

Current source directories:

- `plugins/godot/`
- `plugins/example_runtime/`

Fixed protocol:

- `<plugin-name>.exe -RC`
  Return the Reverie CLI plugin handshake JSON.
- `<plugin-name>.exe -RC-CALL <command> <json-arguments>`
  Execute one plugin command and return a JSON result.

Runtime install root:

- `.reverie/plugins/`

In practice:

1. Write plugin source under `plugins/<plugin-id>/`.
2. Deliver the compiled plugin entry into `.reverie/plugins/<plugin-id>/`.
3. Let Reverie detect it with `/plugins` and inspect it with `/plugins inspect <plugin-id>`.
