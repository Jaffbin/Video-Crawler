# Video Grabber 项目交接档案

> 更新日期：2026-10-28  
> 用途：让接手的开发者或 AI 快速了解产品方向、代码结构、已完成工作、验证情况和接续时的注意事项。  
> 事实来源：当前工作区、README、用户指南、贡献指南、里程碑记录及最近一次实际验证记录。工作区状态会变化；接手时应先重新运行 Git 状态检查。

## 1. 项目概况

Video Grabber 是一个本机运行、以新手易用为目标的视频、音频和图片下载器。界面由 React、TypeScript 和 Tailwind 构成；Python 本机服务通过 yt-dlp 处理下载，并提供 Library、队列管理、诊断及桌面集成。它不要求用户注册，也没有项目自有的云端服务；来源网站和 PyPI 等外部连接按具体功能发生。

产品目标是让普通用户从粘贴链接开始，完成格式和质量选择、下载、查找、预览与可撤销的文件管理，而不要求了解 yt-dlp、命令列或媒体编码细节。产品坚持本机优先：媒体和配置留在用户设备；对于整理和删除操作，优先使用 Recovery、预览和 Undo，避免未经用户确认的永久变更。

## 2. 当前交接状态

### 已完成

- **下载与队列：** 支持视频、MP3、保留来源音频、视频封面和图片直链；队列状态可恢复，支持失败条目重试、批量操作、重复入队检查及现有文件复用确认。
- **Library：** 支持分页、搜索筛选、图片预览、封面优先显示、字幕/封面等伴随文件管理、批量操作、收藏、合集、标签、备注、播放进度和本机媒体导入。
- **Library 整理：** 智能合集和资料整理助手已完成。整理助手检查内容完全相同的文件、记录中缺失的文件及空间概况；结果由用户审核，重复文件不会自动删除，回收操作可撤销。
- **下载易用性：** 首次使用引导、下载偏好预设、备份与预览后合并恢复、检查现有文件、下载前质量/摘要确认等功能已加入。具体边界见用户指南。
- **桌面与通知：** Windows 托盘后台运行、快捷下载窗口、关闭行为设置、批次完成通知及退出时未完成任务提示已实现。Chrome 扩展提供有确认步骤的当前网页/链接发送入口；当前是开发版扩展，不代表已发布到 Chrome Web Store。
- **连续音频播放：** 底部播放器在页面间持续播放；支持播放队列、排序、随机/循环、倍速、跳转和音量。队列、当前曲目及位置保存在本机配置中，重启后暂停恢复；没有睡眠定时器。

### 尚未开始或暂缓

- **M3 可选桌宠快捷入口：** 用户明确要求暂缓，未实现。已讨论的首版方向是 Windows、拖入或粘贴链接、调用现有快捷下载确认面板，不读取 Chrome 当前页；开始前仍需先确认角色素材和动画方案。参见 `docs/MILESTONES.md`。
- 音频队列不包含在当前设置/Library 备份文件中；这是现有功能范围，不要误报为备份已覆盖。
- 发布 Chrome Web Store、应用签名、自动升级等都不是本档案所能确认已完成的发布事项。

## 3. 技术架构与主要入口

### 应用启动和服务端

- `webui.py` 是本机 Web 服务协调层：处理 HTTP API、下载/订阅工作线程、静态资源服务及 Browser/pywebview 启动流程。API 在 `Handler` 中路由；修改接口时同时检查输入校验、路径边界和现有 Host/token 保护。
- `grab.py` 是独立 CLI 下载入口；新手桌面流程通常从 `webui.py` 启动。
- `grab_config.py` 解析服务启动参数；`grab_state.py` 保存线程安全的任务和订阅运行状态；`grab_models.py` 定义任务、订阅等模型；`grab_storage.py` 提供原子 JSON 持久化。
- `grab_download.py` 管理 yt-dlp 条目级失败信息与暂时网络错误分类；下载选项和调用流程仍需以 `grab.py` / `webui.py` 当前实现为准。
- `grab_images.py` 负责图片直链与视频封面下载；临时文件完成后才发布。
- `grab_library.py` 是媒体资料、伴随文件、播放记录和可恢复文件操作的核心。
- `grab_organizer.py` 执行可取消的媒体盘点、内容哈希重复检查和缺失检查；实际文件移动仍交给 `MediaLibrary`，由此复用伴随文件规则和 Undo 流程。
- `grab_backup.py` 维护版本化、字段允许列表化的备份文档与预览后恢复；它不备份媒体本身、凭据、来源 URL、订阅、下载历史或保存目录。
- `grab_desktop.py` 管理托盘、主窗口、快捷下载窗口、关闭行为和桌面生命周期；`grab_notifications.py` 管理 Windows 完成通知。
- `portable_bootstrap.py`、`portable_launcher.py` 和 `scripts/build_portable.ps1` 处理 Windows 便携版构建/启动。Bootstrap 有标准库限制，改依赖安装时应先读 `CONTRIBUTING.md` 和构建脚本。

### 前端

- `frontend/src/App.tsx` 组合主要页面与共享状态；`frontend/src/main.tsx` 是 React 入口；`frontend/src/api/client.ts` 集中封装后端 API。
- `frontend/src/components/` 按下载、队列、Library、布局、音频、诊断等区域组织界面；`frontend/src/lib/` 放可独立测试的业务规则和状态逻辑。
- `frontend/src/lib/audioPlayer.ts` 是音频队列、播放状态转换、本机持久化和单一 HTML audio 元素生命周期的控制器。不要在每个页面各创建一个播放器。播放进度写入带可选 Library root，避免切换媒体库后旧页面覆盖新库进度。
- `frontend/src/lib/smartCollections.ts`、`presets.ts`、`backup.ts`、`libraryBrowse.ts` 等包含可独立验证的规则；跨语言校验有意保留在 Python 和 TypeScript 两侧，因为两边都是输入信任边界。
- `frontend/src/styles.css` 是主要样式入口；界面支持英文、简体中文、繁体中文和日文。
- `webui_dist/` 是前端构建产物，运行预构建应用不要求用户安装 Node.js。改了前端之后要按 `CONTRIBUTING.md` 构建并更新 hashed assets；构建会替换资源文件名，检查 `webui_dist/index.html` 引用和旧资源清理。

### Chrome 扩展

- 源码位于 `browser-extension/chrome/`，Manifest V3；`background.js`、`popup.js`、`connection.js` 和 `entrypoints.js` 复用本机服务协议和确认流程。
- 扩展没有读取所有网站的后台权限；用户主动点击扩展、快捷键或右键菜单后才获取对应页面/链接。改权限或页面注入行为属于安全边界变更，应明确审查。
- `browser-extension/build.py` 生成图标与 ZIP；不要手改生成图标。扩展不依赖前端 npm 构建。

## 4. 数据、隐私和兼容性边界

- 下载、Library、回收区和配置均属于本机数据。测试应使用临时目录、合成媒体和本机 HTTP fixture，不接触真实用户下载、真实账号或私有 cookie。
- 媒体路径、网站 URL、cookie、token 不能写进交接文档、日志样例、测试 fixture 或提交记录。
- `grab_library.py` 是视频、字幕、封面等成组移动/恢复规则的唯一权威来源。新页面或批处理不要复制一份不同的“伴随文件”识别逻辑。
- 备份采用 allowlist，并通过预览 token 绑定用户审阅；恢复是合并，冲突保留当前值，找不到的媒体记录跳过。不要把配置备份误认为媒体备份。
- 文件回收与永久清除是不同操作。重复检查不会自动移动或删除文件；始终保留至少一份并要求用户确认。
- 本机服务有本地鉴权与 Host 检查。API 改动需保留这些检查，并验证请求大小、路径解析、符号链接/reparse point 和失败回滚行为。
- MP4/MP3 与来源音频处理需要可启动的 ffmpeg/ffprobe；Windows 应用控制可能会阻止程序，即使命令行能解析 PATH。Diagnostics 会显示实际解析路径和启动错误；路径配置不能绕过系统策略。
- pywebview、pystray、Pillow、Windows-Toasts 属于 `desktop` extra。开发时若启动时提示缺少 `pystray`，请确认使用了与启动 Video Grabber 相同的 Python 安装 desktop extra；不要只修系统上另一份 Python 环境。

## 5. 工作区与 Git 状态（2026-10-28 检查）

- 当前分支为 `main`，HEAD 为 `82f670d`（`feat: expand downloads, queue recovery and library management`）。
- 检查时工作树包含大量已修改和未跟踪文件，覆盖前后端、测试、扩展、便携构建及音频播放等多个已授权功能。它不是一个干净、只对应最后一项功能的工作区。
- 接手者应先执行 `git status --short` 和 `git diff --stat`，对新增文件也逐一检查；不要运行 `git reset`、清理未跟踪文件、整体 checkout、rebase 或 blanket staging。提交/推送需遵循用户明确授权和仓库流程，本档案不表示有提交或推送。
- 曾讨论 GitHub 推送，但用户要求暂停；接手者不能假设 GitHub 认证或远端推送已经完成。先检查远端状态，不读取、不打印凭据。

## 6. 最近验证记录

以下是 2026-10-27 最近一次音频播放功能完成时实际记录的结果；它们表示当时执行的工作区通过，不保证后续任何改动仍通过。

| 验证 | 结果 |
| --- | --- |
| Python pytest | 557 passed，1 skipped（当前 Windows 账户不能创建目录链接；相关 mock 覆盖通过） |
| 前端 Vitest | 43 个测试文件，232 passed |
| TypeScript typecheck | 通过 |
| Prettier format check | 通过 |
| 前端 production build | 通过；主 JS chunk 约 606 kB，gzip 约 182 kB，有 Vite 体积提示 |
| Ruff | 通过 |
| `git diff --check` | 通过；Windows CRLF 标准化提示不是失败 |
| Edge / WebView2 手动化场景 | 合成 WAV 检查导航后播放、队列排序、随机/循环、倍速、暂停位置恢复、回收/撤销、连续播放及窄窗口；Windows WebView2 最小化后播放与自动切下一首通过 |

M1、M2 里程碑各自的历史验证数和说明在 `docs/MILESTONES.md`；批量回收和扫描性能测量在 `docs/PERFORMANCE_REVIEW.md`。测试历史数字不是当前重新运行的结果。

## 7. 开发环境、命令与注意事项

仓库使用 Python 3.10+、pytest/Ruff、React/TypeScript/Vite/Vitest 和 Node。按 `CONTRIBUTING.md` 创建 `.venv`、安装 `.[dev]`，在 `frontend/` 运行 `npm ci`。用户日常运行无需 Node，因为使用 `webui_dist/`。

```powershell
# 后端
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m pytest -q

# 前端，在 frontend/ 目录执行
npm test
npm run typecheck
npm run format:check
npm run build

# 扩展协议与入口测试，在仓库根目录执行
node --test browser-extension/tests/*.test.js
```

`npm run build` 会写入 `webui_dist/`。不要与检查预构建资源完整性的后端测试并行运行构建，以免测试读到一半更新的静态资源。全套 pytest 的部分本机下载测试可能需要 ffmpeg；大部分其他测试用 fixture，不应依赖私人 cookie 或线上账号。

Windows 便携 ZIP 可用 `powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1` 构建；其依赖下载带有版本与 SHA-256 校验。构建产物位于忽略目录 `artifacts/`。

## 8. 性能与技术债务摘要

已有基准不是生产承诺，但能帮助判断是否值得架构迁移：Library 10,000 条记录的强制扫描在该开发机中从约 4.2 秒降至约 0.9 秒；扫描逻辑减少了对每条记录重复调用 `Path.is_file` 的开销。前端 10,000 项选择成员判断从数组查找的约 1.37 秒降至 Set 查找约 1 毫秒（含建 Set）。200 组回收在 10,000 条元数据时从约 10.6 秒降至约 2.6 秒，元数据保存从 200 次降至 1 次。

已知后续候选：

1. Vite 主 chunk 约 606 kB，存在初始包体积提示；可评估按页面拆分，但要以实际启动/导航性能为目标。
2. Recovery 空间报告会为每个记录枚举匹配文件；大规模回收列表可考虑共享一次目录清单。
3. `/api/state` 仍传递发现的 Library snapshot，由客户端过滤和分页。当前 10,000 项测试没有证明必须改用服务端分页或数据库。
4. `webui.py` 和 `FileGallery.tsx` 较大；后续只按明确职责抽取小模块，先加回归覆盖，不以文件长度为由全面重写。
5. Python 与 TypeScript 重复验证常是安全边界，不应为了去重就删掉其中一侧。详细依据、基准方法和限制见 `docs/PERFORMANCE_REVIEW.md`。

## 9. 推荐接手顺序

1. 重新检查 `git status --short`、`git diff --stat`、`git diff --check`，弄清哪些本地改动必须保留。
2. 阅读 `README.md`（产品与安装）、`docs/USER_GUIDE.md`（已实现用户流程）、`docs/MILESTONES.md`（确认的里程碑）、`docs/PERFORMANCE_REVIEW.md`（测量和边界）及 `CONTRIBUTING.md`（规则和命令）。
3. 若目标是延续产品功能，先向用户确认当前优先级；M3 桌宠明确暂缓，音频播放器已作为额外里程碑完成，不要自行重启被暂缓的桌宠工作。
4. 修改前检查对应模块和相关测试；做完运行有针对性的测试、必要的全套检查，并重新审阅最终 diff。更新用户指南或 README 时只描述实际存在的行为。
5. 每次完成工作后，向用户报告改了什么、验证结果，以及接下来建议做什么；不要暗示没有执行过的命令已通过，也不要自行提交或推送。

## 10. 相关资料

- [README](../README.md)：产品概述、安装、下载模式、CLI 和测试。
- [用户指南](USER_GUIDE.md)：界面操作和用户可见功能。
- [里程碑](MILESTONES.md)：智能合集、资料整理助手、桌宠状态及连续音频播放的边界。
- [性能与代码复用审查](PERFORMANCE_REVIEW.md)：基准结果、取舍及后续候选。
- [贡献指南](../CONTRIBUTING.md)：环境设置、检查命令、模块边界和便携版流程。
- [Chrome 扩展说明](../browser-extension/README.md)：本机连接、权限、安装与开发方式。
