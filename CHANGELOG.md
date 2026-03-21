# CHANGELOG

<!-- version list -->

## v1.1.0 (2026-03-21)

### Bug Fixes

- Add localStorage persistence to image viewer for restore (#81)
  ([#81](https://github.com/pvliesdonk/image-generation-mcp/pull/81),
  [`cc8301a`](https://github.com/pvliesdonk/image-generation-mcp/commit/cc8301a67073fa1018d9f85869dd2f486fe99e9e))

- Cap show_image thumbnail and document client compatibility (#83)
  ([#83](https://github.com/pvliesdonk/image-generation-mcp/pull/83),
  [`6782fbf`](https://github.com/pvliesdonk/image-generation-mcp/commit/6782fbf015540727bda373993eeeed298ec3f43a))

- Disable FastMCP consent page — Authelia handles consent
  ([`6b1afc0`](https://github.com/pvliesdonk/image-generation-mcp/commit/6b1afc0ce5e05c0ec99a81eb92d45a0147cfc94a))

- **a1111**: Split sampler and scheduler for A1111 >=1.6 (#63)
  ([#63](https://github.com/pvliesdonk/image-generation-mcp/pull/63),
  [`a223623`](https://github.com/pvliesdonk/image-generation-mcp/commit/a223623bb40dd51677605010b40a03a4e5a72df0))

- **auth**: Pass required_scopes=[] to MultiAuth (#38) (#41)
  ([#41](https://github.com/pvliesdonk/image-generation-mcp/pull/41),
  [`13487df`](https://github.com/pvliesdonk/image-generation-mcp/commit/13487df7b656f52ba1169bd3df736871647e07b0))

### Chores

- Update server.json to v1.0.0 [skip ci]
  ([`39677ee`](https://github.com/pvliesdonk/image-generation-mcp/commit/39677ee2ae2e25329fdcfe54ccdc66beb85597ab))

### Documentation

- ADR-0007 provider capability model design (#45)
  ([#45](https://github.com/pvliesdonk/image-generation-mcp/pull/45),
  [`6762165`](https://github.com/pvliesdonk/image-generation-mcp/commit/67621659c477941f793550997a0c06800da9e6ac))

- Update design docs and user-facing docs for Milestone 3 (#51)
  ([#51](https://github.com/pvliesdonk/image-generation-mcp/pull/51),
  [`abce3b2`](https://github.com/pvliesdonk/image-generation-mcp/commit/abce3b2e16a892706f0a06911770982db4a2703d))

- **deployment**: Systemd deployment guide (#40) (#44)
  ([#44](https://github.com/pvliesdonk/image-generation-mcp/pull/44),
  [`9c43745`](https://github.com/pvliesdonk/image-generation-mcp/commit/9c43745f5b7bc9ca294aced2c85a4e79416e79d0))

### Features

- Add background transparency parameter to generate_image (#49)
  ([#49](https://github.com/pvliesdonk/image-generation-mcp/pull/49),
  [`226648c`](https://github.com/pvliesdonk/image-generation-mcp/commit/226648c15845dc9b5488d484d4d11bf486fae84c))

- Create_download_link tool with one-time HTTP download URLs (#73)
  ([#73](https://github.com/pvliesdonk/image-generation-mcp/pull/73),
  [`0ed11e8`](https://github.com/pvliesdonk/image-generation-mcp/commit/0ed11e886ad811f2f22e989edef512d3ecd262c3))

- In-memory LRU cache for image resource transforms (#74)
  ([#74](https://github.com/pvliesdonk/image-generation-mcp/pull/74),
  [`aa52dd1`](https://github.com/pvliesdonk/image-generation-mcp/commit/aa52dd1defd935c39e2df418a39f6fe23ffc2c1a))

- Info://prompt-guide resource with per-provider prompt writing guidance (#75)
  ([#75](https://github.com/pvliesdonk/image-generation-mcp/pull/75),
  [`5f3543a`](https://github.com/pvliesdonk/image-generation-mcp/commit/5f3543af424e9817ed4321ac114a453fca2c20af))

- Per-call model selection on generate_image (#71)
  ([#71](https://github.com/pvliesdonk/image-generation-mcp/pull/71),
  [`7293e66`](https://github.com/pvliesdonk/image-generation-mcp/commit/7293e66c4b026d7d87fcc1694f28f37dbfb768c9))

- ProviderCapabilities dataclasses + protocol extension + placeholder impl (#54)
  ([#54](https://github.com/pvliesdonk/image-generation-mcp/pull/54),
  [`897d965`](https://github.com/pvliesdonk/image-generation-mcp/commit/897d9652ddf518c17d3af1589f09358d7fd888a6))

- Split generate_image / show_image into separate tools (#77)
  ([#77](https://github.com/pvliesdonk/image-generation-mcp/pull/77),
  [`9bb178d`](https://github.com/pvliesdonk/image-generation-mcp/commit/9bb178d8d7bff9c4d080d3fefc1e95edc495c6d5))

- Surface provider capabilities in MCP tools, resources, and selector (#50)
  ([#50](https://github.com/pvliesdonk/image-generation-mcp/pull/50),
  [`2b07e5f`](https://github.com/pvliesdonk/image-generation-mcp/commit/2b07e5fab8334b267362ee510e3ccb3fb797e7a4))

- **a1111**: Checkpoint discovery + architecture-aware capabilities (#48)
  ([#48](https://github.com/pvliesdonk/image-generation-mcp/pull/48),
  [`17bb73e`](https://github.com/pvliesdonk/image-generation-mcp/commit/17bb73e5a5ac15fe583eacc28265afeeca97d0f8))

- **apps**: MCP Apps image viewer for generate_image results (#64) (#65)
  ([#65](https://github.com/pvliesdonk/image-generation-mcp/pull/65),
  [`627e3e2`](https://github.com/pvliesdonk/image-generation-mcp/commit/627e3e275f7df9279601d0c6b291e09f7fab246d))

- **openai**: Capability discovery via models.list() (#47)
  ([#47](https://github.com/pvliesdonk/image-generation-mcp/pull/47),
  [`2bc67cd`](https://github.com/pvliesdonk/image-generation-mcp/commit/2bc67cd36bb1a50872d1df209d3f3eaf41a05b9a))

- **packaging**: Linux .deb/.rpm packages with systemd service (#39) (#43)
  ([#43](https://github.com/pvliesdonk/image-generation-mcp/pull/43),
  [`f926a74`](https://github.com/pvliesdonk/image-generation-mcp/commit/f926a74052d57314e3a9083f19cedee0a564ee39))

- **registry**: MCP Registry submission readiness (#37) (#42)
  ([#42](https://github.com/pvliesdonk/image-generation-mcp/pull/42),
  [`345499e`](https://github.com/pvliesdonk/image-generation-mcp/commit/345499ec2fb055e586f218afa152bbcf18dd076f))

- **tools**: Add get_image and list_images tools for tool-only MCP clients (#61)
  ([#61](https://github.com/pvliesdonk/image-generation-mcp/pull/61),
  [`8496e8e`](https://github.com/pvliesdonk/image-generation-mcp/commit/8496e8e0ffed4bffcf3c214f18fe4d3177a3be71))

### Refactoring

- Consolidate onto FastMCP logging stack (#80) (#82)
  ([#82](https://github.com/pvliesdonk/image-generation-mcp/pull/82),
  [`f82799c`](https://github.com/pvliesdonk/image-generation-mcp/commit/f82799c03f36329c7080a7daaf949eee3980cafa))


## v1.0.0 (2026-03-19)

- Initial Release
