# Eidolon SDK fork 与 LiveKit upstream/main 同步审查

日期：2026-09-28。仓库 `eidolon-os/client-sdk-esp32`。`upstream` 指向 `livekit/client-sdk-esp32`，`origin` 指向 Eidolon fork；不向 upstream 推送。

## 分支状态

- `origin/main`：`abd31b0`，以恢复提交撤销误推内容，当前树与 `502ce39` 一致。它不是本项目固件采用的发布分支。
- `origin/eidolon_dev`：`13c780d`，已回退本轮猜测性 SDP 修改，当前树与此前验证的 `3396a5d` 一致。现役固件依赖仍固定在 `3396a5d`。
- 本地 `eidolon_dev`：在上游 `main` 的 `fbf09ed`（LiveKit v0.3.11）之上保留 7 个有效的 Eidolon 提交和本文。最初 rebase 结果 `96cbcdd` 曾包含 3 个互相抵消的 SDP 修改/回退提交；现已从本地历史删除，最终内容与删除前逐字一致。旧状态备份 `backup/eidolon-dev-before-20260928-rebase` 指向 `13c780d`，清理前备份 `backup/eidolon-dev-rebased-with-sdp-reverts-20260928` 指向含这些提交的版本。本地无未提交修改。

本地 rebase 已完成。之后另一次 `git pull -r` 停在清单冲突，没有后台 Git 进程；已取消这条未完成的 rebase，回到已核对的 rebase 结果，避免叠加两次重放。`git merge-base --is-ancestor upstream/main eidolon_dev` 通过，`git range-diff` 已核对原补丁的重放结果。

## 上游实际更新

从先前基线 `29275ba` 到 `fbf09ed` 共 14 个提交，其中 LiveKit 发布为 v0.3.11。对本项目可能有影响的变化：

| 类别 | 上游变化 | 对当前固件的判断 |
| --- | --- | --- |
| WebRTC 底层 | `esp_peer` 约束从 `~1.4.2` 到 `~1.5.5` | 底层二进制行为可能变化；不能据此认定 BOX 协商超时已解决 |
| 信令 | `esp_websocket_client` 从 `~1.7.0` 到 `~1.8.0` | 需要完整构建及设备连接回归 |
| Protobuf | vendored nanopb 更新到 0.4.9.2、组件依赖 `~0.4.9~2` | 需要生成协议和编解码兼容性验证 |
| 示例 | voice_agent Python 示例现代化 | 不属于设备运行路径 |
| 工程 | CI、文档链接、MCP 配置等 | GitHub 推送涉及 workflow 权限 |

上游这段更新**没有改 `components/livekit/core/engine.c` 或 `peer.c`**。Eidolon fork 的净运行代码差异仍是先前已验证的订阅槽释放、按协商配置数据通道、BACKOFF 期间关闭及状态退出顺序。`git diff backup/eidolon-dev-before-20260928-rebase..eidolon_dev -- components/livekit/core/engine.c components/livekit/core/peer.c` 为空；本轮 SDP 日志、内存和重连修改均没有净残留。

三个 rebase 冲突都在 `components/livekit/idf_component.yml`：保留上游 `esp_peer`/WebSocket/nanopb 新依赖，同时保留 Eidolon 的 IDF 6 `cjson` 规则、ESP32-S31 目标以及 `esp_capture ~0.8`、`av_render ~1.0`。组件版本标为 `0.3.11~1`。这只说明依赖声明已合并，未证明组合已能完整构建。

## 验证与发布边界

`python3 -m unittest discover -s tests -v` 的 2 项既有生命周期测试通过。`git diff --exit-code backup/eidolon-dev-before-20260928-rebase eidolon_dev -- components/livekit/core/engine.c components/livekit/core/peer.c` 通过。本地尚未在新 `esp_peer`/WebSocket/nanopb 组合上构建固件，也未刷机或做协商/音频回归。主线三项续聊验收继续使用已验证旧 SDK。

推送初版 rebase 结果时，GitHub 拒绝更新 `.github/workflows/ci.yml`：现有 OAuth token 缺少 `workflow` scope。用户已授权刷新 scope，设备授权尚待完成。远端 `eidolon_dev` 暂停在已安全回退的 `13c780d`。权限完成后应先确认远端仍为 `13c780d`，再用显式 `--force-with-lease` 推送清理后的本地 rebase；不删除上游 CI 文件绕过权限。推送后再安排新依赖的独立构建与设备验证，验证通过前不改现役固件 pin。
