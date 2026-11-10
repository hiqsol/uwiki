# Editors

`uwiki lsp` serves definition, hover, references, outline, completion and check diagnostics over stdio,
links resolving as in every command, see [Concepts](Concepts.md#links).

## Neovim

Neovim 0.11+:

```lua
vim.lsp.config('uwiki', { cmd = { 'uwiki', 'lsp' }, filetypes = { 'markdown' }, root_markers = { 'uwiki.toml' } })
vim.lsp.enable('uwiki')
```
