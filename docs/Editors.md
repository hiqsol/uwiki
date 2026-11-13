# Editors

`uwiki lsp` serves definition, hover, references, outline, completion and check diagnostics over stdio,
links resolving as in every command, see [Concepts](Concepts.md#links);
[refs](Concepts.md#refs) go to their definition, hover shows it or the url, references find every occurrence
and typing a prefix completes the refs the vault defines.

## Neovim

Neovim 0.11+:

```lua
vim.lsp.config('uwiki', { cmd = { 'uwiki', 'lsp' }, filetypes = { 'markdown' }, root_markers = { 'uwiki.toml' } })
vim.lsp.enable('uwiki')
```
