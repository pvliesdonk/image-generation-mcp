# CHANGELOG

<!-- version list -->

## v1.7.0-rc.1 (2026-04-21)

### Bug Fixes

- **packaging**: Add mcpb bundle files (unblocks rc) (#184)
  ([#184](https://github.com/pvliesdonk/image-generation-mcp/pull/184),
  [`0008d24`](https://github.com/pvliesdonk/image-generation-mcp/commit/0008d24330f96cfe65778ac16309a22ea5f5ca27))


## v1.6.0-rc.1 (2026-04-21)

### Chores

- Adopt fastmcp-server-template v1.0.0 + fastmcp-pvl-core (#175)
  ([#175](https://github.com/pvliesdonk/image-generation-mcp/pull/175),
  [`e313d75`](https://github.com/pvliesdonk/image-generation-mcp/commit/e313d757cb4f5383c6b4b6f5203dd0b4ca2bd257))

- Update server.json to v1.5.0 [skip ci]
  ([`1d24411`](https://github.com/pvliesdonk/image-generation-mcp/commit/1d24411d5d9cfb0d39c6701e323c1a22d525f3ba))


## v1.5.0 (2026-04-01)

### Chores

- Update server.json to v1.4.0 [skip ci]
  ([`e551b01`](https://github.com/pvliesdonk/image-generation-mcp/commit/e551b01f2becbec5b4a3764a0b6a438c11501a52))

- **deps**: Bump fastmcp from 3.1.1 to 3.2.0 (#166)
  ([#166](https://github.com/pvliesdonk/image-generation-mcp/pull/166),
  [`8a98e85`](https://github.com/pvliesdonk/image-generation-mcp/commit/8a98e852e617628787264bfa031b05411e3e3b09))

- **deps**: Bump requests from 2.32.5 to 2.33.0 (#155)
  ([#155](https://github.com/pvliesdonk/image-generation-mcp/pull/155),
  [`7ef4557`](https://github.com/pvliesdonk/image-generation-mcp/commit/7ef45574d67165e69fe0992af99023a61bdc64f0))

### Documentation

- Fix prompts.md intro to count all three prompts (#163)
  ([#163](https://github.com/pvliesdonk/image-generation-mcp/pull/163),
  [`a205f03`](https://github.com/pvliesdonk/image-generation-mcp/commit/a205f038f0918731d24603288d51f525ab4fd41a))

- Update provider selection with live test findings (#167)
  ([#167](https://github.com/pvliesdonk/image-generation-mcp/pull/167),
  [`cd1ce26`](https://github.com/pvliesdonk/image-generation-mcp/commit/cd1ce262dfd2138c003c84b9afe6621655b0cad9))

### Features

- Add check_generation_status tool to avoid polling UI clutter (#161)
  ([#161](https://github.com/pvliesdonk/image-generation-mcp/pull/161),
  [`3065742`](https://github.com/pvliesdonk/image-generation-mcp/commit/306574217991987cd5240e8bc8357b89fc308e28))

- Gemini image generation provider (#160)
  ([#160](https://github.com/pvliesdonk/image-generation-mcp/pull/160),
  [`f4b463c`](https://github.com/pvliesdonk/image-generation-mcp/commit/f4b463c6d23323013fec75a1ea11862d5b326d58))

- Image transforms (crop/rotate/flip) + interactive editor (#156)
  ([#156](https://github.com/pvliesdonk/image-generation-mcp/pull/156),
  [`a621d12`](https://github.com/pvliesdonk/image-generation-mcp/commit/a621d12a302688044f06229e72064a15bdd9f83a))

- Wire up quality parameter to real API behavior (Gemini + OpenAI) (#165)
  ([#165](https://github.com/pvliesdonk/image-generation-mcp/pull/165),
  [`6031224`](https://github.com/pvliesdonk/image-generation-mcp/commit/60312246ec7e3089b45b386f79ad102e89900b8d))

### Performance Improvements

- Bundle ext-apps SDK to eliminate CDN dependency (#153)
  ([#153](https://github.com/pvliesdonk/image-generation-mcp/pull/153),
  [`e3c030e`](https://github.com/pvliesdonk/image-generation-mcp/commit/e3c030eca6a6728d0a3ed7e15ee8ce895130f936))


## v1.4.0 (2026-03-25)

### Bug Fixes

- Address architect-reviewer findings
  ([`aa1cb25`](https://github.com/pvliesdonk/image-generation-mcp/commit/aa1cb2517dfd96dbd8b1f614a6000f219092611a))

- Improve critical LLM-facing tool descriptions (#146)
  ([#146](https://github.com/pvliesdonk/image-generation-mcp/pull/146),
  [`6eb63cb`](https://github.com/pvliesdonk/image-generation-mcp/commit/6eb63cbe8cf0dc1ad0482d65ea261b1b057baefa))

- Polish secondary LLM-facing descriptions (#147)
  ([#147](https://github.com/pvliesdonk/image-generation-mcp/pull/147),
  [`aab9e79`](https://github.com/pvliesdonk/image-generation-mcp/commit/aab9e790437f568dbdffea42a303fd664cbe7fde))

- **ci**: Ignore CVE-2026-4539 in pip-audit (pygments, no fix available)
  ([`7e00d98`](https://github.com/pvliesdonk/image-generation-mcp/commit/7e00d98cd7f2e62a80278e466d7464f5051a9e02))

- **gallery**: Disable autoResize, use sendSizeChanged for frame height (#148)
  ([#148](https://github.com/pvliesdonk/image-generation-mcp/pull/148),
  [`1d08f31`](https://github.com/pvliesdonk/image-generation-mcp/commit/1d08f31c06f1a40c453ae3edcc3128501288aafd))

- **gallery**: Update callServerTool to {name,arguments} API, bump ext-apps to 1.3.1 (#140)
  ([#140](https://github.com/pvliesdonk/image-generation-mcp/pull/140),
  [`3516b77`](https://github.com/pvliesdonk/image-generation-mcp/commit/3516b77680b020cda681dfffc73ccbb82e6990c4))

- **widget**: Auto-compute Claude sandbox domain from BASE_URL
  ([`e0c69e3`](https://github.com/pvliesdonk/image-generation-mcp/commit/e0c69e32469811654115be3fcc39208b02a14897))

- **widget**: Correct LRU eviction order and restore console.warn (#132)
  ([#132](https://github.com/pvliesdonk/image-generation-mcp/pull/132),
  [`de990fa`](https://github.com/pvliesdonk/image-generation-mcp/commit/de990fa8823b7258918ffaf885e9905034359f74))

- **widget**: Derive MCP Apps domain from BASE_URL hostname (#127)
  ([#127](https://github.com/pvliesdonk/image-generation-mcp/pull/127),
  [`9f5c5d9`](https://github.com/pvliesdonk/image-generation-mcp/commit/9f5c5d928993a6ea5fde477bd3e043112f9cfeee))

- **widget**: Drop host-specific domain, use APP_DOMAIN env var
  ([`9922d7d`](https://github.com/pvliesdonk/image-generation-mcp/commit/9922d7dd0c54867aeea423bea8aad58a229a9592))

### Chores

- Update server.json to v1.3.0 [skip ci]
  ([`1a41d8f`](https://github.com/pvliesdonk/image-generation-mcp/commit/1a41d8f66b442e1af20b9843cc3747cb13e0e0a1))

### Documentation

- Add APP_DOMAIN env var and Claude hash computation
  ([`d8a4f24`](https://github.com/pvliesdonk/image-generation-mcp/commit/d8a4f246a83b103a8859a358fdb7fc9ce0a25e1e))

### Features

- Add server-level palette icon for MCP client UIs (#149)
  ([#149](https://github.com/pvliesdonk/image-generation-mcp/pull/149),
  [`a64e57e`](https://github.com/pvliesdonk/image-generation-mcp/commit/a64e57e8f47d0ae3d82765a2c285f46edbbfcf24))

- **gallery**: Add browse_gallery tool, gallery_page app-only tool, and gallery HTML resource (#133)
  ([#133](https://github.com/pvliesdonk/image-generation-mcp/pull/133),
  [`733b45f`](https://github.com/pvliesdonk/image-generation-mcp/commit/733b45fab9fa9701a30bbc6756c3c9cc6647cbce))

- **gallery**: Add delete_image tool and gallery delete buttons (#135)
  ([#135](https://github.com/pvliesdonk/image-generation-mcp/pull/135),
  [`68e20ea`](https://github.com/pvliesdonk/image-generation-mcp/commit/68e20ea632aa34b617b3d624fdcdb4e595b6d96e))

- **gallery**: Add lightbox zoom view and gallery_full_image app-only tool (#134)
  ([#134](https://github.com/pvliesdonk/image-generation-mcp/pull/134),
  [`2c9fab0`](https://github.com/pvliesdonk/image-generation-mcp/commit/2c9fab0e173a6fdbc767dcbe5eae7817e2d824f3))

- **gallery**: Add picture-in-picture (PiP) display mode (#142)
  ([#142](https://github.com/pvliesdonk/image-generation-mcp/pull/142),
  [`cdbbe3b`](https://github.com/pvliesdonk/image-generation-mcp/commit/cdbbe3ba53c450a0ec51df458f368f9940bc5d99))

- **http**: Add JSON-RPC-aware request logging middleware
  ([`5711c18`](https://github.com/pvliesdonk/image-generation-mcp/commit/5711c187e213b809e8f7b3097c3658f804d5f633))

- **http**: Add persistent EventStore for HTTP session resumability (#138)
  ([#138](https://github.com/pvliesdonk/image-generation-mcp/pull/138),
  [`27f181f`](https://github.com/pvliesdonk/image-generation-mcp/commit/27f181f24bdc884aa0145c5b23b3950ed7b66fb5))

- **http**: Log clientInfo, resource URIs, and User-Agent
  ([`7d28114`](https://github.com/pvliesdonk/image-generation-mcp/commit/7d28114ae05252aebc228c9c846bcfcbb4018072))

- **widget**: Add download button via ext-apps downloadFile API
  ([`8261f26`](https://github.com/pvliesdonk/image-generation-mcp/commit/8261f265ef5669bef0a6b64193399c98d088ec6a))

- **widget**: Redesign image viewer following ext-apps SDK patterns
  ([`fc2028c`](https://github.com/pvliesdonk/image-generation-mcp/commit/fc2028c2086935a0f7e46681d7a6a49820615fee))

- **widget**: Redesign MCP Apps image viewer with ext-apps SDK (#128)
  ([#128](https://github.com/pvliesdonk/image-generation-mcp/pull/128),
  [`213e058`](https://github.com/pvliesdonk/image-generation-mcp/commit/213e05887b6537a812dd42b265848cc79deb4e49))

- **widget**: Show generating/failed status instead of empty frame
  ([`5cf6a21`](https://github.com/pvliesdonk/image-generation-mcp/commit/5cf6a21cdcade993d46e1f47966cb696f636b79e))


## v1.3.0 (2026-03-24)

### Bug Fixes

- Add Flux prompt guidance and prompt_style metadata (#114) (#115)
  ([#115](https://github.com/pvliesdonk/image-generation-mcp/pull/115),
  [`546bc04`](https://github.com/pvliesdonk/image-generation-mcp/commit/546bc0482a0cd19e5df028b752cee700f33bd27a))

- Add force_refresh and refreshed_at to list_providers (#113) (#116)
  ([#116](https://github.com/pvliesdonk/image-generation-mcp/pull/116),
  [`e8e0478`](https://github.com/pvliesdonk/image-generation-mcp/commit/e8e0478d78d8a6a1dbf6cb53cfdc9a793f633179))

- Add MCP tool annotations and widget domain for ChatGPT compatibility (#121)
  ([#121](https://github.com/pvliesdonk/image-generation-mcp/pull/121),
  [`f23a8cf`](https://github.com/pvliesdonk/image-generation-mcp/commit/f23a8cfce7e149850f5807ecdb1fc6dca4aa6295))

- Set project GitHub URL as widget domain for ChatGPT app identity (#125)
  ([#125](https://github.com/pvliesdonk/image-generation-mcp/pull/125),
  [`72c0981`](https://github.com/pvliesdonk/image-generation-mcp/commit/72c098135d03406eb5808b35c90638d761686bde))

- Shorten server.json description for MCP registry 100-char limit (#103)
  ([#103](https://github.com/pvliesdonk/image-generation-mcp/pull/103),
  [`79ee6d0`](https://github.com/pvliesdonk/image-generation-mcp/commit/79ee6d042bb359c2560957aca63fce18882fdb3e))

- **widget**: Remove non-functional download button from image viewer (#123)
  ([#123](https://github.com/pvliesdonk/image-generation-mcp/pull/123),
  [`f5ca2a9`](https://github.com/pvliesdonk/image-generation-mcp/commit/f5ca2a94d8e16a636e82403db4771c8e4fb8a7ef))

### Chores

- Adopt shared infrastructure improvements from markdown-vault-mcp (#111)
  ([#111](https://github.com/pvliesdonk/image-generation-mcp/pull/111),
  [`d2c6956`](https://github.com/pvliesdonk/image-generation-mcp/commit/d2c695617fda1d1f3998d3b6d740c322b711edf2))

- Update server.json to v1.2.0 [skip ci]
  ([`b4a4bf8`](https://github.com/pvliesdonk/image-generation-mcp/commit/b4a4bf8cff294be3731875d474b980122d2517f7))

### Documentation

- Update Authelia setup for remote auth mode and Claude Code client config (#105)
  ([#105](https://github.com/pvliesdonk/image-generation-mcp/pull/105),
  [`a9e582f`](https://github.com/pvliesdonk/image-generation-mcp/commit/a9e582f8a65fe6e4221241493b27eb40528e2dac))

### Features

- Fire-and-forget async generation (#112) (#117)
  ([#117](https://github.com/pvliesdonk/image-generation-mcp/pull/117),
  [`fa6f661`](https://github.com/pvliesdonk/image-generation-mcp/commit/fa6f661ba849028f21f055b0be9cccdcb90151f2))

- **sd_webui**: Add Flux dev/schnell model presets (#109)
  ([#109](https://github.com/pvliesdonk/image-generation-mcp/pull/109),
  [`b05128b`](https://github.com/pvliesdonk/image-generation-mcp/commit/b05128b46af833dfd7b359bdd57297792c1f03a4))

- **sd_webui**: Add progress polling via /sdapi/v1/progress (#76) (#118)
  ([#118](https://github.com/pvliesdonk/image-generation-mcp/pull/118),
  [`434fea3`](https://github.com/pvliesdonk/image-generation-mcp/commit/434fea38d5c276258b3299fe0d728d605a992bbe))

### Refactoring

- Rename a1111 provider to sd-webui (#108)
  ([#108](https://github.com/pvliesdonk/image-generation-mcp/pull/108),
  [`2c389ff`](https://github.com/pvliesdonk/image-generation-mcp/commit/2c389ff23489c13556a50722ec1ac4eab649d82c))


## v1.2.0 (2026-03-22)

### Bug Fixes

- Add MCP-level keepalives during image generation to prevent client timeouts (#95) (#96)
  ([#96](https://github.com/pvliesdonk/image-generation-mcp/pull/96),
  [`3f6a91c`](https://github.com/pvliesdonk/image-generation-mcp/commit/3f6a91cd6a75931e95e0a17898b58266ca4387bf))

- Release pipeline failures in publish-linux-packages and publish-registry (#97) (#98)
  ([#98](https://github.com/pvliesdonk/image-generation-mcp/pull/98),
  [`cdf9c60`](https://github.com/pvliesdonk/image-generation-mcp/commit/cdf9c60720d0167bfc040d6fe07986149982acec))

- **ci**: Replace Codecov cloud dependency with local diff-cover for patch coverage gate (#102)
  ([#102](https://github.com/pvliesdonk/image-generation-mcp/pull/102),
  [`2f9030f`](https://github.com/pvliesdonk/image-generation-mcp/commit/2f9030ffdc76ab8a183b8b00efd1de31b9ddb865))

### Chores

- Update server.json to v1.1.0 [skip ci]
  ([`5611d24`](https://github.com/pvliesdonk/image-generation-mcp/commit/5611d24787c4d2c86d255454b95e66fe341875fd))

### Features

- Elicitation confirmation for paid image providers (#88)
  ([#88](https://github.com/pvliesdonk/image-generation-mcp/pull/88),
  [`d4580fb`](https://github.com/pvliesdonk/image-generation-mcp/commit/d4580fba2d0e4371d30b2f91322df7398ed3e76d))

- Show model name and auto-generate download link in show_image (#87)
  ([#87](https://github.com/pvliesdonk/image-generation-mcp/pull/87),
  [`ac66c4b`](https://github.com/pvliesdonk/image-generation-mcp/commit/ac66c4bfe18d91abd2e05dd60ba2eaa1ecd94bc2))

- Support RemoteAuthProvider as default OIDC mode (#99) (#100)
  ([#100](https://github.com/pvliesdonk/image-generation-mcp/pull/100),
  [`cb1d669`](https://github.com/pvliesdonk/image-generation-mcp/commit/cb1d6694e63eeff976e440ef0586a51ea9a6dbb3))

### Refactoring

- Derive ProviderCapabilities.supports_* as properties from models (#53) (#91)
  ([#91](https://github.com/pvliesdonk/image-generation-mcp/pull/91),
  [`eb9eb4c`](https://github.com/pvliesdonk/image-generation-mcp/commit/eb9eb4c013ea09243a8b614509cf84a91e9b2142))

- Move config tests from test_transform_cache.py to test_config.py (#89) (#90)
  ([#90](https://github.com/pvliesdonk/image-generation-mcp/pull/90),
  [`41020ba`](https://github.com/pvliesdonk/image-generation-mcp/commit/41020ba95d6f2ad79816d34358a7660093fec107))

- Parallelize A1111 discovery API calls with asyncio.gather (#52) (#92)
  ([#92](https://github.com/pvliesdonk/image-generation-mcp/pull/92),
  [`72f3449`](https://github.com/pvliesdonk/image-generation-mcp/commit/72f34497cb99ef9637a4c82fe2662f6bc9b8c22f))

### Testing

- Add MCP-level integration tests for image resources and generate_image tool (#22) (#93)
  ([#93](https://github.com/pvliesdonk/image-generation-mcp/pull/93),
  [`ffc5e71`](https://github.com/pvliesdonk/image-generation-mcp/commit/ffc5e71600141ab3b1e025271ab7795fdbe427bd))

- Raise test coverage to 80% with meaningful tests (#36) (#94)
  ([#94](https://github.com/pvliesdonk/image-generation-mcp/pull/94),
  [`e866604`](https://github.com/pvliesdonk/image-generation-mcp/commit/e86660463ff9f8e871b908bdfe3bfa8ee02b656d))


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
